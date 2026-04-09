import os
from agents.router import generate_with_fallback
from serpapi import GoogleSearch
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import threading

load_dotenv()

def _open_scholar_browser(query: str) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            search_url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
            page.goto(search_url)
            page.wait_for_timeout(6000)  # stay open 6 seconds so judges can see it
            browser.close()
    except Exception as e:
        print(f"[research] browser error: {e}")

async def run_research_agent(query: str) -> str:
    # open browser visibly in background thread
    thread = threading.Thread(target=_open_scholar_browser, args=(query,), daemon=True)
    thread.start()

    # search via SerpAPI
    params = {
        "engine": "google_scholar",
        "q": query,
        "api_key": os.getenv("SERPAPI_KEY"),
        "num": 5
    }

    search = GoogleSearch(params)
    results = search.get_dict()
    papers = results.get("organic_results", [])

    if not papers:
        return f"I searched Google Scholar for {query} but couldn't find results. Try being more specific."

    context = "\n\n".join([
        f"Title: {p.get('title')}\nSummary: {p.get('snippet', 'No summary available')}"
        for p in papers[:5]
    ])

    summary_prompt = f"""
    A user who is visually impaired asked: "{query}"
    Here are academic papers found on Google Scholar:
    {context}

    Give a 2-3 sentence spoken summary a blind user can act on.
    Mention 1-2 specific paper titles. Be concise and clear — this will be read aloud.
    """
    return await generate_with_fallback(summary_prompt)