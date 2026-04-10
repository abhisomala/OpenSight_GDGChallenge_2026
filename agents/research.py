import os
import threading
from agents.router import generate_with_fallback
from serpapi import GoogleSearch
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

_active_browser: dict | None = None

def close_active_browser():
    global _active_browser
    if _active_browser:
        _active_browser["close"] = True
        _active_browser = None

research_memory = {
    "last_papers": [],
    "last_query": "",
}


def _open_scholar_browser(query: str, result_holder: dict) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=680,780",
                "--window-position=720,60",
            ])
            page = browser.new_page()
            search_url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
            page.goto(search_url)
            page.wait_for_load_state("domcontentloaded")

            while not result_holder.get("close"):
                page.wait_for_timeout(500)

            browser.close()
    except Exception as e:
        print(f"[research] browser error: {e}")


def _is_followup(query: str) -> bool:
    q = query.lower()

    if research_memory["last_papers"] and len(q.split()) < 6:
        return True

    return any(phrase in q for phrase in [
        "author", "who wrote", "who made", "first paper", "second paper",
        "third paper", "that paper", "the paper", "tell me more", "more about",
        "methodology", "findings", "published", "journal", "when was",
        "what year", "cite", "citation", "abstract", "summary of that",
        "that study", "that research", "the study", "the research",
        "what did", "what does", "how many", "where was", "what is it about",
    ])


async def run_research_agent(query: str, history: list = []) -> str:
    global _active_browser, research_memory

    if _is_followup(query) and research_memory["last_papers"]:
        print(f"[research] follow-up detected, answering from memory")

        context = "\n\n".join([
            f"Paper {i+1}:\nTitle: {p.get('title')}\n"
            f"Authors: {p.get('publication_info', {}).get('authors', [{}])[0].get('name', 'Unknown') if p.get('publication_info', {}).get('authors') else 'Not available'}\n"
            f"Summary: {p.get('snippet', 'No summary')}\n"
            f"Year: {p.get('publication_info', {}).get('summary', '')}"
            for i, p in enumerate(research_memory["last_papers"][:5])
        ])

        history_text = ""
        if history:
            history_text = "\n\nRecent conversation:\n"
            for turn in history:
                history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

        prompt = f"""
You are OpenSight, a voice assistant. The user previously searched for "{research_memory['last_query']}" and these papers were found:

{context}
{history_text}

The user is now asking: "{query}"

Answer their follow-up question directly using the paper details above.
Keep it to 2-3 sentences max, spoken naturally. No bullet points or markdown.
"""
        return await generate_with_fallback(prompt)

    # new search
    print(f"[research] new search: {query}")

    result_holder = {"close": False}
    _active_browser = result_holder
    threading.Thread(
        target=_open_scholar_browser,
        args=(query, result_holder),
        daemon=True,
    ).start()

    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": os.getenv("SERPAPI_KEY"),
        "num": 5,
    }

    search = GoogleSearch(params)
    results = search.get_dict()
    papers = results.get("organic_results", [])

    if not papers:
        return f"I searched Google Scholar for {query} but couldn't find results. Try being more specific."

    research_memory["last_papers"] = papers
    research_memory["last_query"] = query

    context = "\n\n".join([
        f"Title: {p.get('title')}\nSummary: {p.get('snippet', 'No summary available')}"
        for p in papers[:5]
    ])

    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    summary_prompt = f"""
A user asked: "{query}"
{history_text}
Here are academic papers found on Google Scholar:
{context}

Give a 2-3 sentence spoken summary. Mention 1-2 specific paper titles by name.
Be concise and clear — this will be read aloud.
"""
    return await generate_with_fallback(summary_prompt)