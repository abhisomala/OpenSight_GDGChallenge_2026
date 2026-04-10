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
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            context = browser.new_context(viewport={"width": 720, "height": 900})
            page = context.new_page()
            search_url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
            page.goto(search_url)
            page.wait_for_load_state("domcontentloaded")

            while not result_holder.get("close"):
                page.wait_for_timeout(500)

            browser.close()
    except Exception as e:
        print(f"[research] browser error: {e}")


def _shorten_title(title: str) -> str:
    title = title.split(':')[0].strip()
    if len(title) > 50:
        title = title[:50].rsplit(' ', 1)[0]
    return title


def _build_response(papers: list) -> str:
    if not papers:
        return "I couldn't find any papers on that."
    p1 = _shorten_title(papers[0].get('title', 'Unknown'))
    if len(papers) == 1:
        return f"Found one paper — {p1}. Want to know more about it?"
    p2 = _shorten_title(papers[1].get('title', 'Unknown'))
    return f"Got two papers. First is {p1}, and second is {p2}. Want to know more about either?"


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
You are a voice assistant. Answer conversationally in 1-2 sentences.
No filler phrases, no bullet points, no markdown.
Get straight to the answer using only what's relevant below.

Papers on "{research_memory['last_query']}":
{context}
{history_text}
User: "{query}"
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
        return f"I couldn't find anything on {query}. Try a different search term."

    research_memory["last_papers"] = papers
    research_memory["last_query"] = query

    return _build_response(papers)