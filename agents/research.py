import os
import re
import threading
from agents.router import generate_with_fallback
from serpapi import GoogleSearch
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import browser_manager

load_dotenv()

research_memory = {
    "last_papers": [],
    "last_query": "",
    "scholar_browser_close": None,
}

_NEW_SEARCH_TRIGGERS = re.compile(
    r"^(research|find research|search for|look up|find papers|find studies|find me research|"
    r"find me papers|show me research|show me papers|get me research|"
    r"search papers|search studies|look for papers|look for research)\b",
    re.IGNORECASE,
)


def close_active_browser():
    fn = research_memory.get("scholar_browser_close")
    if fn:
        try:
            fn()
        except Exception:
            pass
        research_memory["scholar_browser_close"] = None


def _shorten_title(title: str) -> str:
    title = title.split(':')[0].strip()
    if len(title) > 50:
        title = title[:50].rsplit(' ', 1)[0]
    return title


def _extract_product_hint(papers: list, query: str) -> str:
    mappings = [
        (r"omega.?3|fish oil|dha|epa",         "omega-3 fish oil supplement"),
        (r"magnesium",                           "magnesium supplement"),
        (r"vitamin\s*d",                         "vitamin D supplement"),
        (r"melatonin|sleep",                     "melatonin sleep supplement"),
        (r"probiotics?|gut",                     "probiotic supplement"),
        (r"curcumin|turmeric",                   "turmeric curcumin supplement"),
        (r"creatine",                            "creatine supplement"),
        (r"collagen",                            "collagen supplement"),
        (r"zinc",                                "zinc supplement"),
        (r"vitamin\s*c|ascorb",                  "vitamin C supplement"),
        (r"b12|cobalamin",                       "vitamin B12 supplement"),
        (r"iron",                                "iron supplement"),
        (r"caffeine|coffee",                     "caffeine supplement"),
        (r"protein",                             "protein supplement"),
        (r"ashwagandha|adaptogen",               "ashwagandha supplement"),
        (r"berberine",                           "berberine supplement"),
        (r"resveratrol",                         "resveratrol supplement"),
        (r"CoQ10|coenzyme",                      "CoQ10 supplement"),
    ]
    full_text = query + " " + " ".join(p.get("title", "") for p in papers[:3])
    for pattern, hint in mappings:
        if re.search(pattern, full_text, re.IGNORECASE):
            return hint
    stopwords = {"what", "find", "show", "tell", "about", "papers", "research",
                 "study", "some", "give", "recent", "latest", "effects",
                 "impact", "role", "the", "and", "for", "on", "of", "in"}
    words = [w for w in query.split() if len(w) > 3 and w.lower() not in stopwords]
    return " ".join(words[:3]) + " supplement" if words else ""


def _build_response(papers: list) -> str:
    if not papers:
        return "I couldn't find any papers on that."
    p1 = _shorten_title(papers[0].get('title', 'Unknown'))
    if len(papers) == 1:
        return f"Found one paper — {p1}. Want to know more about it?"
    p2 = _shorten_title(papers[1].get('title', 'Unknown'))
    return f"Got two papers. First is {p1}, and second is {p2}. Want to know more about either?"


def _is_new_search(query: str) -> bool:
    return bool(_NEW_SEARCH_TRIGGERS.search(query.strip()))


def _is_followup(query: str) -> bool:
    if not research_memory["last_papers"] or not research_memory["last_query"]:
        return False
    if _is_new_search(query):
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


def _launch_scholar_browser(url: str, holder: dict) -> None:
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
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception as nav_err:
                print(f"[research] scholar nav note: {nav_err}")

            # grab HWND and bring browser to front
            hwnd = browser_manager._find_chromium_hwnd(timeout=6.0)
            if hwnd:
                browser_manager.set_browser_hwnd(hwnd)
                browser_manager.focus_browser()

            while not holder.get("close"):
                page.wait_for_timeout(500)
            browser.close()
    except Exception as e:
        print(f"[research] scholar browser error: {e}")
    finally:
        holder["done"] = True


def _launch_paper_window(link: str) -> None:
    browser_manager.close_all()
    holder: dict = {"close": False, "done": False}

    def _close():
        holder["close"] = True

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            context = browser.new_context(
                accept_downloads=True,
                viewport={"width": 720, "height": 900},
            )
            page = context.new_page()
            browser_manager.register(_close)
            research_memory["scholar_browser_close"] = _close
            try:
                page.goto(link, wait_until="domcontentloaded", timeout=15000)
            except Exception as nav_err:
                print(f"[research] paper nav note: {nav_err}")

            # grab HWND and bring browser to front
            hwnd = browser_manager._find_chromium_hwnd(timeout=6.0)
            if hwnd:
                browser_manager.set_browser_hwnd(hwnd)
                browser_manager.focus_browser()

            while not holder.get("close"):
                page.wait_for_timeout(500)
            browser.close()
    except Exception as e:
        print(f"[research] paper window error: {e}")


def _open_paper(index: int) -> str:
    papers = research_memory["last_papers"]
    if index >= len(papers):
        return "I don't have that paper."
    link = papers[index].get("link", "")
    title = _shorten_title(papers[index].get("title", "Paper"))
    if not link:
        return "I don't have a link for that paper."
    threading.Thread(target=_launch_paper_window, args=(link,), daemon=True).start()
    return f"Opening {title} now."


def _open_scholar_results(query: str) -> None:
    browser_manager.close_all()
    url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
    holder: dict = {"close": False, "done": False}

    def _close():
        holder["close"] = True

    research_memory["scholar_browser_close"] = _close
    browser_manager.register(_close)
    threading.Thread(target=_launch_scholar_browser, args=(url, holder), daemon=True).start()
    print(f"[research] opened Scholar tab: {url}")


async def run_research_agent(query: str, history: list = [], status_cb=None, memory=None) -> str:
    global research_memory

    async def _status(msg: str):
        if status_cb:
            try:
                await status_cb(msg)
            except Exception as e:
                print(f"[research] status error: {e}")

    if _is_followup(query) and research_memory["last_papers"]:
        q = query.lower()
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

        mem_context_block = ""
        if memory is not None:
            ctx = memory.context_for_prompt()
            if ctx and ctx != "No prior context.":
                mem_context_block = f"\n\nSESSION CONTEXT:\n{ctx}\n"

        prompt = f"""
You are a voice assistant. Answer conversationally in 1-2 sentences.
No filler phrases, no bullet points, no markdown.
Get straight to the answer using only what's relevant below.
{mem_context_block}
Papers on "{research_memory['last_query']}":
{context}
{history_text}
User: "{query}"
"""
        await _status("Composing response...")
        result = await generate_with_fallback(prompt)
        if memory is not None:
            memory.set_result("research", result)
            memory.add_turn("assistant", result, agent="research")
        return result

    print(f"[research] new search: {query}")
    await _status("Building search query...")

    clean_query = re.sub(
        r"^(research on|find research on|find papers on|find studies on|search for|look up)\s+",
        "", query.strip(), flags=re.IGNORECASE
    )

    params = {
        "engine": "google_scholar",
        "q": clean_query,
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
        return f"I couldn't find anything on {clean_query}. Try a different search term."

    await _status(f"Found {len(papers)} papers · ranking by relevance...")

    research_memory["last_papers"] = papers
    research_memory["last_query"] = clean_query
    resp = _build_response(papers)
    print(f"[research] done: {resp[:60]}")

    _open_scholar_results(clean_query)

    if memory is not None:
        memory.set_result("research", resp)
        memory.add_turn("assistant", resp, agent="research")

        product_hint = _extract_product_hint(papers, clean_query)
        if product_hint:
            memory.entities["product_hint"] = product_hint
            print(f"[research] product_hint stored: {product_hint}")

        stopwords = {"what", "find", "show", "tell", "about", "papers", "research",
                     "study", "some", "give", "recent", "latest", "best", "good"}
        new_topics = [w.lower() for w in clean_query.split()
                      if len(w) > 3 and w.lower() not in stopwords]
        existing = set(memory.entities.get("topics", []))
        for t in new_topics:
            if t not in existing:
                memory.entities["topics"].append(t)
                existing.add(t)

    return resp