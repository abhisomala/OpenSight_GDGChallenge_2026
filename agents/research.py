"""Search Google Scholar via SerpAPI and synthesize research responses.

Playwright execution (Scholar browser, paper windows) has moved to desktop_browser.py.
This module handles server-side logic: SerpAPI calls, response synthesis, and followup
detection using the in-memory research_memory cache.
"""
import asyncio
import os
import re
from typing import Optional
from agents.router import generate_with_fallback
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

research_memory: dict = {
    "last_papers": [],
    "last_query": "",
}

_NEW_SEARCH_TRIGGERS = re.compile(
    r"^(research|find research|search for|look up|find papers|find studies|find me research|"
    r"find me papers|show me research|show me papers|get me research|"
    r"search papers|search studies|look for papers|look for research)\b",
    re.IGNORECASE,
)

_FOLLOWUP_KEYWORDS = re.compile(
    r"\b(author|authors|who wrote|who made|methodology|method|findings|finding|"
    r"published|journal|when was|cite|abstract|summary|conclusion|"
    r"tell me more|more about|what did they|how did they|their approach|"
    r"first paper|second paper|that paper|the paper|that study|the study|"
    r"that research|the research|open|pull up|launch|show me|"
    r"second one|first one|that one|the first|the second)\b",
    re.IGNORECASE,
)


def _shorten_title(title: str) -> str:
    title = title.split(':')[0].strip()
    if len(title) > 50:
        title = title[:50].rsplit(' ', 1)[0]
    return title


def _extract_product_hint(papers: list, query: str) -> str:
    """Infer a shopping hint from research papers and the query."""
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
    """Detect follow-up questions about earlier research results."""
    if not research_memory["last_papers"] or not research_memory["last_query"]:
        return False
    if _is_new_search(query):
        return False
    return bool(_FOLLOWUP_KEYWORDS.search(query))


def get_open_intent(query: str) -> tuple[bool, Optional[str]]:
    """Detect whether a followup query wants to open a paper. Returns (wants_open, url_or_None).

    Called by server.py before run_research_agent so open-paper followups can be
    dispatched as browser_action RESEARCH_OPEN without entering the followup text path.
    """
    q = query.lower()
    wants_open = any(w in q for w in ["open", "pull up", "launch", "show me"])
    if not wants_open:
        return False, None

    papers = research_memory.get("last_papers", [])
    if not papers:
        return True, None  # wants_open but nothing cached

    open_index: Optional[int] = None
    if any(w in q for w in ["second", "2nd"]):
        open_index = 1
    elif any(w in q for w in ["third", "3rd"]):
        open_index = 2
    elif any(w in q for w in ["first", "1st", "the first"]):
        open_index = 0
    elif any(w in q for w in ["that one", "this one", "the one"]):
        open_index = 0
    elif len(papers) == 1:
        open_index = 0

    if open_index is None or open_index >= len(papers):
        return True, None  # ambiguous — caller should ask "which one?"

    url = papers[open_index].get("link", "")
    return True, url if url else None


async def search_scholar(
    query: str,
    status_cb=None,
) -> tuple[list, str, str]:
    """Call SerpAPI to find papers. Returns (papers, scholar_url, clean_query).

    Does NOT open a browser — Playwright execution is handled by the desktop client
    via browser_action RESEARCH after this function returns.
    """
    async def _status(msg: str):
        if status_cb:
            try:
                await status_cb(msg)
            except Exception:
                pass

    await _status("Building search query...")

    clean_query = re.sub(
        r"^(research on|find research on|find papers on|find studies on|search for|look up)\s+",
        "", query.strip(), flags=re.IGNORECASE,
    )

    scholar_url = f"https://scholar.google.com/scholar?q={clean_query.replace(' ', '+')}"

    params = {
        "engine": "google_scholar",
        "q": clean_query,
        "api_key": os.getenv("SERPAPI_KEY"),
        "num": 5,
    }

    await _status("Searching Google Scholar...")
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None,
        lambda: GoogleSearch(params).get_dict(),
    )
    papers = results.get("organic_results", [])

    if papers:
        await _status(f"Found {len(papers)} papers · ranking by relevance...")

    return papers, scholar_url, clean_query


def synthesize_research_response(
    papers: list,
    clean_query: str,
    memory=None,
) -> str:
    """Build spoken response from papers, populate research_memory, update session memory.

    Called by server.py after search_scholar returns. Papers come from SerpAPI
    (server-side); browser opening is handled separately via browser_action RESEARCH.
    """
    if not papers:
        return f"I couldn't find anything on {clean_query}. Try a different search term."

    research_memory["last_papers"] = papers
    research_memory["last_query"] = clean_query

    resp = _build_response(papers)

    if memory is not None:
        memory.set_result("research", resp)
        memory.add_turn("assistant", resp, agent="research")

        product_hint = _extract_product_hint(papers, clean_query)
        if product_hint:
            memory.entities["product_hint"] = product_hint

        stopwords = {"what", "find", "show", "tell", "about", "papers", "research",
                     "study", "some", "give", "recent", "latest", "best", "good"}
        memory.entities.setdefault("topics", [])
        existing = set(memory.entities["topics"])
        new_topics = [w.lower() for w in clean_query.split()
                      if len(w) > 3 and w.lower() not in stopwords]
        for t in new_topics:
            if t not in existing:
                memory.entities["topics"].append(t)
                existing.add(t)

    return resp


async def run_research_agent(
    query: str,
    history: list | None = None,
    status_cb=None,
    memory=None,
) -> str:
    """Handle text-based followup questions about cached research papers.

    New searches go through search_scholar + synthesize_research_response in server.py.
    Open-paper followups go through browser_action RESEARCH_OPEN in server.py.
    This function is called only for text-based followups (authors, findings, etc.).
    """
    history = history or []

    async def _status(msg: str):
        if status_cb:
            try:
                await status_cb(msg)
            except Exception:
                print("[research] status error")

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
