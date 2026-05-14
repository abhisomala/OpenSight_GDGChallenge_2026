"""Answer general questions with Google search and Gemini synthesis."""
import os
import re
import aiohttp
from agents.router import generate_with_fallback

SYSTEM_PROMPT = """
You are OpenSight, a helpful voice assistant. You have been given information to answer the user's question accurately.
Keep responses to 2-3 sentences max — they will be read aloud.
Do not use bullet points, lists, or markdown. Speak naturally.
Base your answer on the information provided. If it doesn't help, say so honestly.
"""

_CONTEXT_RE = re.compile(r'\[context:\s*([^\]]+)\]', re.IGNORECASE)


def _parse_query(raw_query: str) -> tuple[str, str]:
    """Split a query from any product context block."""
    match = _CONTEXT_RE.search(raw_query)
    if not match:
        return raw_query.strip(), ""
    product_raw = match.group(1).strip()
    product_name = re.sub(r'^user is looking at\s*', '', product_raw, flags=re.IGNORECASE).strip()
    clean_question = _CONTEXT_RE.sub('', raw_query).strip()
    return clean_question, product_name


def _clean_product_name(name: str) -> str:
    """Clean product names for search and answer prompts."""
    name = re.sub(r'[®™©]', '', name)
    name = re.split(r'\s[-|]\s', name)[0]
    words = name.strip().split()
    if words:
        last = words[-1].rstrip('.,')
        if len(last) < 4 or not re.search(r'[aeiouAEIOU]', last):
            words = words[:-1]
    return " ".join(words).strip()


def _build_search_query(clean_question: str, product_name: str) -> str:
    """Build a focused Google search query."""
    if not product_name:
        return clean_question
    product = _clean_product_name(product_name)
    keywords = re.findall(
        r'\b(ingredient|ingredients|nutrition|calories|calorie|allergen|allergens|'
        r'contain|contains|made of|what.s in|protein|carbs|fat|sugar|sodium|fiber|'
        r'review|reviews|rating|ratings|side effect|dosage|dose)\b',
        clean_question, re.IGNORECASE
    )
    key = keywords[0].lower() if keywords else "ingredients"
    return f"{product} {key}"


def _get_scraped_product_info() -> dict:
    """Pull whatever was scraped from the currently open product page."""
    try:
        from agents.shopping import get_open_product_details
        return get_open_product_details()
    except Exception:
        return {}


def _build_scraped_context(details: dict, question: str) -> str:
    """
    Turn scraped product details into a concise context block for the prompt.
    Picks the most relevant fields based on the question.
    """
    parts = []
    if details.get("title"):
        parts.append(f"Product: {details['title']}")

    q_lower = question.lower()
    wants_ingredients = any(w in q_lower for w in [
        "ingredient", "ingredients", "contain", "made of", "what's in", "what is in"
    ])
    wants_nutrition = any(w in q_lower for w in [
        "calorie", "calories", "protein", "carbs", "fat", "sugar", "sodium", "fiber", "nutrition"
    ])

    if wants_ingredients or wants_nutrition:
        if details.get("ingredients"):
            parts.append(f"Ingredients: {details['ingredients']}")
        elif details.get("bullets"):
            relevant = [b for b in details["bullets"] if any(
                w in b.lower() for w in ["ingredient", "contain", "made", "natural", "fish", "oil",
                                          "calorie", "protein", "carb", "fat", "sugar", "sodium"]
            )]
            if relevant:
                parts.append("Product details: " + " | ".join(relevant[:4]))
            else:
                parts.append("Product features: " + " | ".join(details["bullets"][:4]))
    else:
        if details.get("bullets"):
            parts.append("Product features: " + " | ".join(details["bullets"][:5]))

    return "\n".join(parts)


async def _search_web(query: str) -> str:
    """Search Google Custom Search and return compact snippets."""
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_CX")
    if not api_key or not cx:
        return ""
    try:
        params = {"key": api_key, "cx": cx, "q": query, "num": 5}
        async with aiohttp.ClientSession() as session:
            # Google technology: Google Custom Search API.
            async with session.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=aiohttp.ClientTimeout(total=8.0),
            ) as resp:
                data = await resp.json()
                items = data.get("items", [])
                if not items:
                    return ""
                return "\n\n".join([
                    f"Title: {item.get('title')}\nSnippet: {item.get('snippet')}"
                    for item in items
                ])
    except Exception as e:
        print(f"[general] search error: {e}")
        return ""


async def run_general_agent(query: str, history: list = [], memory=None) -> str:
    """Answer from scraped data, search results, or Gemini."""
    clean_question, product_name = _parse_query(query)

    # ── check scraped product page first ──────────────────────────────────────
    scraped = _get_scraped_product_info()
    scraped_context = ""

    if scraped and (scraped.get("ingredients") or scraped.get("bullets")):
        scraped_context = _build_scraped_context(scraped, clean_question)

    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    mem_context_block = ""
    if memory is not None:
        ctx = memory.context_for_prompt()
        if ctx and ctx != "No prior context.":
            mem_context_block = f"\n\nSESSION CONTEXT:\n{ctx}\n"

    product_context_block = ""
    if product_name:
        product_context_block = f"\n\nPRODUCT IN FOCUS: {_clean_product_name(product_name)}\n"

    if scraped_context:
        prompt = (
            f"{SYSTEM_PROMPT}{mem_context_block}{product_context_block}{history_text}"
            f"\n\nINFORMATION FROM THE OPEN PRODUCT PAGE:\n{scraped_context}"
            f"\n\nAnswer this based on the product page information above: {clean_question}"
        )
    else:
        search_query = _build_search_query(clean_question, product_name)
        search_results = await _search_web(search_query)

        if search_results:
            prompt = (
                f"{SYSTEM_PROMPT}{mem_context_block}{product_context_block}{history_text}"
                f"\n\nSearch results for '{search_query}':\n{search_results}"
                f"\n\nUser: {clean_question}"
            )
        else:
            prompt = (
                f"{SYSTEM_PROMPT}{mem_context_block}{product_context_block}{history_text}"
                f"\n\nUser: {clean_question}"
                f"\n\n(No information available, use your training knowledge about "
                f"{_clean_product_name(product_name) if product_name else 'this product'}.)"
            )

    result = await generate_with_fallback(prompt)
    if memory is not None:
        memory.set_result("general", result)
        memory.add_turn("assistant", result, agent="general")
    return result