import os
import json
import re
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

SYSTEM_PROMPT = """
You are a planner for a voice assistant called OpenSight.
Given a user message, determine if it requires one or multiple steps to complete.

Available agents:
- SHOPPING: finding, comparing, buying, or searching for products on Amazon. Always preserve price constraints exactly as stated by the user (e.g. "under $800", "less than $500").
- CALENDAR: scheduling, booking, checking or creating Google Calendar events
- RESEARCH: finding academic papers or studies on a topic. Also use RESEARCH for any follow-up questions about papers that were previously mentioned, such as asking about authors, methodology, findings, or details of a specific paper.
- GENERAL: greetings, follow-up questions, definitions, opinions, math, weather, jokes, anything that doesn't require browsing Amazon, accessing a calendar, or finding academic papers. When in doubt use GENERAL.

Respond ONLY with a JSON object like this:

For a single step:
{
  "steps": [
    {"intent": "SHOPPING", "query": "good laptop under $500"}
  ]
}

For multiple steps:
{
  "steps": [
    {"intent": "RESEARCH", "query": "best laptops for machine learning"},
    {"intent": "SHOPPING", "query": "{{PREVIOUS_RESULT}}"}
  ]
}

Use "{{PREVIOUS_RESULT}}" as a placeholder when a step depends on the output of the previous step.
Always return valid JSON with a "steps" array. Never return anything else.
Keep all responses under 3 sentences. Be direct and concise.
"""

# ── Follow-up pattern matchers ─────────────────────────────────────────────────

RESEARCH_FOLLOWUP_PATTERN = re.compile(
    r"\b(author|who wrote|who made|first paper|second paper|that paper|the paper|tell me more|methodology|findings|published|journal|when was)\b",
    re.IGNORECASE,
)

SHOPPING_FOLLOWUP_PATTERN = re.compile(
    r"\b(open|click|buy|select|choose|option\s*\d+|first|second|third|1st|2nd|3rd|that one|this one|the first one|the second one|the third one|repeat|tell me more|more about)\b",
    re.IGNORECASE,
)

SHOPPING_INTENT_PATTERN = re.compile(
    r"\b(find|get|buy|order|search|look for|shop|show me|recommend|suggest|pick)\b.{0,30}\b(on amazon|supplement|product|pill|capsule|tablet|powder|oil|cream|gear|device|gadget|book|item)\b"
    r"|\b(on amazon|under \$|less than \$|for under|find me|get me|buy me|order me)\b",
    re.IGNORECASE,
)

PRODUCT_CONTEXT_PATTERN = re.compile(
    r"\b(ingredient|ingredients|nutrition|calories|allergen|contain|made of|what.s in|what is in|how much|serving|protein|carb|fat|sugar|sodium|fiber|review|rating|how many star)\b",
    re.IGNORECASE,
)


def _has_recent_research_context(history: list | None, memory=None) -> bool:
    """Check history AND memory for a recent research result."""
    if memory is not None and memory.entities.get("product_hint"):
        return True
    if not history:
        return False
    for turn in history[-3:]:
        assistant_text = str(turn.get("assistant", "")).lower()
        if any(phrase in assistant_text for phrase in [
            "research", "paper", "study", "journal", "published", "authors",
            "got two papers", "found one paper", "i found",
        ]):
            return True
    return False


def _has_recent_shopping_context(history: list | None, shopping_memory: dict | None = None) -> bool:
    if shopping_memory and shopping_memory.get("last_results"):
        return True
    if not history:
        return False
    for turn in history[-3:]:
        assistant_text = str(turn.get("assistant", "")).lower()
        if any(phrase in assistant_text for phrase in [
            "option", "found", "amazon", "$", "which one", "opening",
            "i found", "two options", "three options", "got two", "got three",
            "for $", "at $", "going for",
        ]):
            return True
    return False


# ── Gemini helpers ─────────────────────────────────────────────────────────────

async def generate_with_fallback(contents: str) -> str:
    for model in MODELS:
        try:
            response = client.models.generate_content(model=model, contents=contents)
            return response.text.strip()
        except Exception as e:
            print(f"[gemini] {model} failed: {e}, trying next...")
    raise Exception("All Gemini models unavailable")


async def extract_preferences(query: str, memory) -> None:
    if len(query.split()) < 4:
        return
    prompt = (
        'Extract any user preferences or constraints from this query.\n'
        'Return JSON only — no explanation, no markdown:\n'
        '{"budget": null, "allergies": [], "diet": [], "topics": []}\n'
        'If nothing is found, return all nulls/empty arrays.\n'
        f'Query: {query}'
    )
    try:
        raw = re.sub(r"```json|```", "", await generate_with_fallback(prompt)).strip()
        prefs = json.loads(raw)
        new_prefs: dict = {}
        if prefs.get("budget") is not None:
            new_prefs["budget"] = prefs["budget"]
        if prefs.get("allergies"):
            existing = memory.preferences.get("allergies", [])
            new_prefs["allergies"] = list(set(existing + prefs["allergies"]))
        if prefs.get("diet"):
            diet = prefs["diet"]
            if isinstance(diet, str):
                diet = [diet]
            existing = memory.preferences.get("diet", [])
            new_prefs["diet"] = list(set(existing + diet))
        if new_prefs:
            memory.update_preferences(new_prefs)
        topics = prefs.get("topics") or []
        existing_topics = set(memory.entities.get("topics", []))
        for t in topics:
            if t and t not in existing_topics:
                memory.entities["topics"].append(t)
                existing_topics.add(t)
    except Exception as e:
        print(f"[router] preference extraction skipped: {e}")


# ── Main planner ───────────────────────────────────────────────────────────────

async def plan_intent(
    user_text: str,
    history: list | None = None,
    memory=None,
    shopping_memory: dict | None = None,
) -> list:
    history = history or []

    if memory is not None:
        await extract_preferences(user_text, memory)

    # ── product context question on an open Amazon page → GENERAL ──
    if PRODUCT_CONTEXT_PATTERN.search(user_text) and _has_recent_shopping_context(history, shopping_memory):
        last_product = ""
        if shopping_memory and shopping_memory.get("last_results"):
            last_product = shopping_memory["last_results"][0].get("title", "")
        enriched = f"{user_text} [context: user is looking at {last_product}]" if last_product else user_text
        print(f"[router] product context question detected, routing to GENERAL")
        return [{"intent": "GENERAL", "query": enriched}]

    # ── shopping follow-up: pass original query unchanged ──
    if _has_recent_shopping_context(history, shopping_memory) and SHOPPING_FOLLOWUP_PATTERN.search(user_text):
        print(f"[router] shopping follow-up detected, passing original query through")
        return [{"intent": "SHOPPING", "query": user_text}]

    # ── cross-agent: research → shopping handoff ──
    # User says something shopping-intent after a research turn → inject product_hint
    if _has_recent_research_context(history, memory) and SHOPPING_INTENT_PATTERN.search(user_text):
        product_hint = ""
        if memory is not None:
            product_hint = memory.entities.get("product_hint", "")

        if product_hint:
            # preserve any price constraint the user stated
            price_match = re.search(
                r"(under \$[\d]+|less than \$[\d]+|below \$[\d]+|under [\d]+|for under \$[\d]+)",
                user_text, re.IGNORECASE
            )
            price_clause = f" {price_match.group(0)}" if price_match else ""
            enriched_query = f"{product_hint}{price_clause}"
            print(f"[router] research→shopping handoff: '{enriched_query}'")
            return [{"intent": "SHOPPING", "query": enriched_query}]
        else:
            # no hint stored yet — still route to shopping with original query
            print(f"[router] research→shopping handoff (no hint), passing query through")
            return [{"intent": "SHOPPING", "query": user_text}]

    # ── research follow-up: enrich with last research context ──
    if _has_recent_research_context(history, memory) and RESEARCH_FOLLOWUP_PATTERN.search(user_text):
        last_research = ""
        for turn in reversed(history):
            if any(phrase in turn.get("assistant", "").lower() for phrase in
                   ["paper", "study", "research", "journal"]):
                last_research = turn.get("assistant", "")
                break
        enriched_query = f"{user_text} [context: {last_research}]" if last_research else user_text
        return [{"intent": "RESEARCH", "query": enriched_query}]

    # ── general Gemini routing ──
    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    memory_context = ""
    if memory is not None:
        ctx = memory.context_for_prompt()
        if ctx and ctx != "No prior context.":
            memory_context = f"\n\nSESSION CONTEXT (use this to understand follow-ups and user preferences):\n{ctx}"

    raw = re.sub(r"```json|```", "", await generate_with_fallback(
        f"{SYSTEM_PROMPT}{history_text}{memory_context}\n\nUser message: {user_text}"
    )).strip()

    if not raw:
        return [{"intent": "GENERAL", "query": user_text}]
    try:
        data = json.loads(raw)
        return data.get("steps", [{"intent": "GENERAL", "query": user_text}])
    except json.JSONDecodeError:
        return [{"intent": "GENERAL", "query": user_text}]