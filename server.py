"""FastAPI WebSocket server that routes messages to OpenSight agents."""
import asyncio
import sys
import json
import os
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.shopping import (
    run_shopping_agent,
    synthesize_shopping_response,
    set_open_product_details,
    _is_followup_query,
    _is_open_intent,
    _extract_option_index,
    get_followup_product_url,
    get_followup_product_title,
)
from agents.calendar import run_calendar_agent
from agents.research import (
    run_research_agent,
    search_scholar,
    synthesize_research_response,
    _is_followup as _is_research_followup,
    get_open_intent as _get_research_open_intent,
    research_memory,
)
from agents.general import run_general_agent
from agents.router import plan_intent, generate_with_fallback
from dotenv import load_dotenv
from memory import SessionMemory
import browser_manager

# Removed: duplicate `import sys` (was on line 19 in original)
# Removed: `from agents.research import research_memory, _is_followup`
#   — no longer needed; routing is now fully owned by plan_intent in router.py
# Removed: close_shopping_browser, close_research_browser, close_calendar_browser
#   — these were imported but never called; browsers close via browser_manager.close_all()

if "--fresh" in sys.argv:
    for f in ["shopping_memory.json", "conversation_history.json", "opensight_memory.json"]:
        if os.path.exists(f):
            os.remove(f)
    sys.argv.remove("--fresh")

if sys.platform == "win32":
    # WindowsProactorEventLoopPolicy is deprecated in Python 3.14+.
    # DefaultEventLoopPolicy is correct for Python 3.11+ on Windows.
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

load_dotenv()

import base64

# Decode Google TTS credentials from env var when running on Cloud Run
if os.getenv("GOOGLE_TTS_CREDENTIALS_B64"):
    with open("tts_credentials.json", "wb") as f:
        f.write(base64.b64decode(os.getenv("GOOGLE_TTS_CREDENTIALS_B64")))

app = FastAPI()

AGENT_LABELS = {
    "BRAIN": "routing",
    "SHOPPING": "searching Amazon",
    "CALENDAR": "checking your calendar",
    "RESEARCH": "searching research papers",
    "GENERAL": "thinking",
}

SHOPPING_MEMORY_FILE = "shopping_memory.json"
CONVERSATION_HISTORY_FILE = "conversation_history.json"


def _load_shopping_memory() -> dict:
    try:
        if os.path.exists(SHOPPING_MEMORY_FILE):
            with open(SHOPPING_MEMORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"last_query": "", "last_results": []}


def _save_shopping_memory(mem: dict) -> None:
    try:
        with open(SHOPPING_MEMORY_FILE, "w") as f:
            json.dump(mem, f)
    except Exception:
        print("[opensight] could not save shopping memory")


def _load_conversation_history() -> list:
    try:
        if os.path.exists(CONVERSATION_HISTORY_FILE):
            with open(CONVERSATION_HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_conversation_history(history: list) -> None:
    try:
        with open(CONVERSATION_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        print("[opensight] could not save conversation history")


# ── Persistent state ───────────────────────────────────────────────────────────
_conversation_history: list = _load_conversation_history()
_shopping_memory: dict = _load_shopping_memory()
_last_intent: str = ""
_session_memory: SessionMemory = SessionMemory.load()


def close_all_browsers():
    browser_manager.close_all()


def _is_short_actionable_text(text: str, shopping_mem: dict) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    has_options = bool((shopping_mem or {}).get("last_results"))
    if not has_options:
        return False
    return any([
        "option" in t,
        any(word in t for word in ["first", "second", "third", "1st", "2nd", "3rd"]),
        any(word in t for word in ["open", "click", "buy", "select", "choose"]),
        "that one" in t,
        "this one" in t,
    ])


_ACTIONABLE_SHORT = re.compile(
    r"\b(first|second|third|1st|2nd|3rd|open|yes|no|stop|repeat|"
    r"select|choose|buy|next|back|that one|this one|option)\b",
    re.IGNORECASE,
)


def _is_garbled(text: str) -> bool:
    words = text.split()
    if len(words) < 3 and not _ACTIONABLE_SHORT.search(text):
        return True
    if text.strip().endswith("?") and len(words) < 2:
        return True
    fragments = ["can you", "try finding", "in?", "that in"]
    if sum(1 for f in fragments if f in text.lower()) >= 2:
        return True
    return False


async def send_status(ws: WebSocket, agent: str, state: str, detail: str = "") -> None:
    await ws.send_text(json.dumps({
        "type": "status",
        "agent": agent,
        "state": state,
        "detail": detail,
    }))


async def _wait_for_browser_result(ws: WebSocket, agent_name: str, timeout: float = 120.0) -> dict:
    """Wait for a browser_result message with the matching agent name.

    Only used for SHOPPING new searches where the server needs the results data
    before it can synthesize the response. All other browser actions are fire-and-forget.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=5.0)
            msg = json.loads(raw)
            if msg.get("type") == "browser_result" and msg.get("agent") == agent_name:
                return msg.get("data", {})
        except asyncio.TimeoutError:
            continue
        except WebSocketDisconnect:
            break
        except Exception:
            break
    return {}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Handle one OpenSight client WebSocket session."""
    global _conversation_history, _shopping_memory, _last_intent, _session_memory

    await ws.accept()
    print("[opensight] client connected")


    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            user_text = message.get("text", "")

            if _is_garbled(user_text) or (
                len(user_text.split()) < 3
                and not _is_short_actionable_text(user_text, _shopping_memory)
            ):
                await ws.send_text(json.dumps({
                    "type": "response",
                    "text": "I didn't catch that. Could you say that again?"
                }))
                await send_status(ws, "IDLE", "idle")
                continue

            print("[opensight] received user message")
            await send_status(ws, "BRAIN", "thinking", "routing")

            _session_memory.add_turn("user", user_text)

            try:
                steps = await plan_intent(
                    user_text,
                    _conversation_history,
                    memory=_session_memory,
                    shopping_memory=_shopping_memory,
                )

                all_responses = []
                previous_result = ""

                for step in steps:
                    intent = step.get("intent", "GENERAL")
                    query = step.get("query", user_text)

                    if "{{PREVIOUS_RESULT}}" in query and previous_result:
                        query = query.replace("{{PREVIOUS_RESULT}}", previous_result)

                    label = AGENT_LABELS.get(intent, "thinking")
                    await send_status(
                        ws,
                        intent if intent in AGENT_LABELS else "GENERAL",
                        "thinking",
                        label,
                    )

                    async def _research_status(msg: str):
                        try:
                            await ws.send_text(json.dumps({"type": "research_status", "text": msg}))
                        except Exception:
                            pass

                    # ── SHOPPING ───────────────────────────────────────────────
                    if intent == "SHOPPING":
                        if _is_followup_query(query) and _shopping_memory.get("last_results"):
                            if _is_open_intent(query):
                                # Open a specific product — send browser_action, fire-and-forget
                                product_url = get_followup_product_url(query, _shopping_memory)
                                product_title = get_followup_product_title(query, _shopping_memory)
                                if product_url:
                                    await ws.send_text(json.dumps({
                                        "type": "browser_action",
                                        "agent": "SHOPPING_OPEN",
                                        "url": product_url,
                                    }))
                                    # Wait for scraped data from desktop client
                                    scraped = await _wait_for_browser_result(ws, "SHOPPING_OPEN", timeout=30.0)
                                    if scraped:
                                        set_open_product_details(scraped.get("scraped", {}))
                                    result = f"Opening the {product_title} now."
                                else:
                                    result = "Which one — the first, second, or third?"
                                memory_update = None
                            else:
                                # Text-only followup (repeat, tell me more, ordinal without open)
                                result, memory_update = await run_shopping_agent(
                                    query, _shopping_memory, memory=_session_memory
                                )
                        else:
                            # New Amazon search — must wait for browser_result to get results
                            await ws.send_text(json.dumps({
                                "type": "browser_action",
                                "agent": "SHOPPING",
                                "query": query,
                            }))
                            browser_data = await _wait_for_browser_result(ws, "SHOPPING")
                            result, memory_update = synthesize_shopping_response(
                                browser_data, query, _shopping_memory, _session_memory
                            )

                    # ── RESEARCH ──────────────────────────────────────────────
                    elif intent == "RESEARCH":
                        if _is_research_followup(query):
                            wants_open, paper_url = _get_research_open_intent(query)
                            if wants_open:
                                papers = research_memory.get("last_papers", [])
                                if paper_url:
                                    # Fire-and-forget: open paper on client, respond immediately
                                    await ws.send_text(json.dumps({
                                        "type": "browser_action",
                                        "agent": "RESEARCH_OPEN",
                                        "url": paper_url,
                                    }))
                                    result = "Opening that paper now."
                                elif not papers:
                                    result = "I don't have any papers cached."
                                elif len(papers) == 1:
                                    url = papers[0].get("link", "")
                                    if url:
                                        await ws.send_text(json.dumps({
                                            "type": "browser_action",
                                            "agent": "RESEARCH_OPEN",
                                            "url": url,
                                        }))
                                        result = "Opening that paper now."
                                    else:
                                        result = "I don't have a link for that paper."
                                else:
                                    result = "Which one — the first or the second?"
                            else:
                                # Text-based followup (authors, methodology, findings…)
                                result = await run_research_agent(
                                    query, _conversation_history,
                                    status_cb=_research_status,
                                    memory=_session_memory,
                                )
                            memory_update = None
                        else:
                            # New Scholar search — SerpAPI stays server-side
                            papers, scholar_url, clean_query = await search_scholar(
                                query, status_cb=_research_status
                            )
                            result = synthesize_research_response(
                                papers, clean_query, memory=_session_memory
                            )
                            if papers:
                                # Fire-and-forget: open Scholar on client, respond immediately
                                await ws.send_text(json.dumps({
                                    "type": "browser_action",
                                    "agent": "RESEARCH",
                                    "url": scholar_url,
                                }))
                            memory_update = None

                    # ── CALENDAR ──────────────────────────────────────────────
                    elif intent == "CALENDAR":
                        result = await run_calendar_agent(query, memory=_session_memory)
                        memory_update = None

                    # ── GENERAL ───────────────────────────────────────────────
                    else:
                        result = await run_general_agent(
                            query, _conversation_history, memory=_session_memory
                        )
                        memory_update = None

                    _last_intent = intent
                    all_responses.append(result)
                    previous_result = result

                    if intent == "SHOPPING" and memory_update is not None:
                        _shopping_memory.update(memory_update)
                        _save_shopping_memory(_shopping_memory)

                if len(all_responses) == 1:
                    final_response = all_responses[0]
                else:
                    combine_prompt = (
                        "Combine these into one 2-sentence spoken response. No filler. No lists.\n"
                        + "\n".join(all_responses)
                    )
                    final_response = await generate_with_fallback(combine_prompt)

            except Exception as e:
                final_response = f"Sorry, I ran into an issue: {str(e)}"
                print("[opensight] error")

            _conversation_history.append({"user": user_text, "assistant": final_response})
            if len(_conversation_history) > 10:
                _conversation_history.pop(0)

            _save_conversation_history(_conversation_history)
            _session_memory.last_query = user_text
            _session_memory.save()

            await ws.send_text(json.dumps({"type": "response", "text": final_response}))
            await send_status(ws, "IDLE", "idle")

    except WebSocketDisconnect:
        print("[opensight] client disconnected")
