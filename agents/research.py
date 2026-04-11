import os
import threading
from agents.router import generate_with_fallback
from serpapi import GoogleSearch
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

_active_browser: dict | None = None
_scholar_page = None

research_memory = {
    "last_papers": [],
    "last_query": "",
}


def close_active_browser():
    global _active_browser
    if _active_browser:
        _active_browser["close"] = True
        _active_browser = None


def _open_scholar_browser(query: str, result_holder: dict) -> None:
    global _scholar_page
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
            _scholar_page = page
            search_url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
            page.goto(search_url)
            page.wait_for_load_state("domcontentloaded")
            while not result_holder.get("close"):
                page.wait_for_timeout(500)
            browser.close()
            _scholar_page = None
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
    if not research_memory["last_papers"] or not research_memory["last_query"]:
        return False

    if len(query.split()) < 6:
        return True

    return any(phrase in query.lower() for phrase in [
        "author", "who wrote", "tell me more", "more about",
        "first paper", "second paper", "that paper", "the paper",
        "methodology", "findings", "published", "when was",
        "cite", "abstract", "that study", "the research",
        "what method", "how did they", "what did they", "did they use",
        "their approach", "their method", "how does it", "what is it",
        "open", "open up", "open the", "show me", "pull up",
        "second one", "first one", "that one",
    ])


def _launch_paper_window(link: str) -> None:
    """Open paper in a positioned Chromium window matching the Scholar panel."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            page = browser.new_page()
            page.goto(link)
            page.wait_for_timeout(60000)
            browser.close()
    except Exception as e:
        print(f"[research] paper window error: {e}")


def _open_paper(index: int) -> str:
    global _scholar_page
    print(f"[research] opening paper {index}, scholar_page={_scholar_page is not None}")
    papers = research_memory["last_papers"]
    if index >= len(papers):
        return "I don't have that paper."
    link = papers[index].get("link", "")
    title = _shorten_title(papers[index].get("title", "Paper"))
    if not link:
        return "I don't have a link for that paper."

    # try navigating the existing Scholar window first
    if _scholar_page:
        try:
            _scholar_page.goto(link)
            return f"Opening {title} now."
        except Exception as e:
            print(f"[research] scholar nav error: {e}")

    # fallback — open in a new positioned Chromium window same as Scholar
    threading.Thread(target=_launch_paper_window, args=(link,), daemon=True).start()
    return f"Opening {title} now."


async def run_research_agent(query: str, history: list = [], status_cb=None) -> str:
    global _active_browser, research_memory

    async def _status(msg: str):
        if status_cb:
            try:
                await status_cb(msg)
            except Exception as e:
                print(f"[research] status error: {e}")

    # ── follow-up / open paper path ──
    if _is_followup(query) and research_memory["last_papers"]:
        q = query.lower()

        # detect open intent
        wants_open = any(w in q for w in ["open", "pull up", "launch", "show me"])
        open_index = None
        if any(w in q for w in ["second", "2nd"]):
            open_index = 1
        elif any(w in q for w in ["third", "3rd"]):
            open_index = 2
        elif any(w in q for w in ["first", "1st"]):
            open_index = 0
        elif any(w in q for w in ["that one", "this one", "the one"]):
            open_index = 0

        if wants_open and open_index is not None:
            return _open_paper(open_index)

        # ── general follow-up — answer from memory ──
        print(f"[research] follow-up detected, answering from memory")
        await _status(f"Answering from memory · {len(research_memory['last_papers'])} papers cached")

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
        await _status("Composing response...")
        return await generate_with_fallback(prompt)

    # ── new search path ──
    print(f"[research] new search: {query}")
    await _status("Building search query...")

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

    await _status("Searching Google Scholar...")
    print("[research] hitting SerpAPI...")
    search = GoogleSearch(params)
    results = search.get_dict()
    print(f"[research] SerpAPI done, got {len(results.get('organic_results', []))} results")
    papers = results.get("organic_results", [])

    if not papers:
        return f"I couldn't find anything on {query}. Try a different search term."

    await _status(f"Found {len(papers)} papers · ranking by relevance...")

    print("[research] about to build response...")
    research_memory["last_papers"] = papers
    research_memory["last_query"] = query
    resp = _build_response(papers)
    print(f"[research] done: {resp[:60]}")
    return resp