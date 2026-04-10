import os
import httpx
import threading
from agents.router import generate_with_fallback
from playwright.sync_api import sync_playwright

SYSTEM_PROMPT = """
You are OpenSight, a helpful voice assistant. You have been given web search results to answer the user's question accurately.
Keep responses to 2-3 sentences max — they will be read aloud.
Do not use bullet points, lists, or markdown. Speak naturally.
Base your answer on the search results provided. If the results don't help, say so honestly.
"""

def _open_search_browser(search_url: str) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=680,780",
                "--window-position=720,60",
            ])
            page = browser.new_page()
            page.goto(search_url)
            page.wait_for_timeout(10000)
            browser.close()
    except Exception as e:
        print(f"[general] browser error: {e}")


async def _search_web(query: str) -> str:
    api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_SEARCH_CX")

    if not api_key or not cx:
        return ""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cx, "q": query, "num": 5},
                timeout=8.0,
            )
            data = resp.json()
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


async def run_general_agent(query: str, history: list = []) -> str:
    # search the web for current info
    search_results = await _search_web(query)

    # open browser in background showing search results
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    threading.Thread(
        target=_open_search_browser,
        args=(search_url,),
        daemon=True,
    ).start()

    # build history context
    history_text = ""
    if history:
        history_text = "\n\nRecent conversation:\n"
        for turn in history:
            history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n"

    # build prompt with search results
    if search_results:
        prompt = f"{SYSTEM_PROMPT}{history_text}\n\nSearch results for '{query}':\n{search_results}\n\nUser: {query}"
    else:
        prompt = f"{SYSTEM_PROMPT}{history_text}\n\nUser: {query}\n\n(No web results available, use your training knowledge.)"

    return await generate_with_fallback(prompt)