import asyncio
import sys
import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.shopping import run_shopping_agent
from agents.calendar import run_calendar_agent
from agents.research import run_research_agent, research_memory, _is_followup
from agents.general import run_general_agent
from agents.router import plan_intent, generate_with_fallback
from agents.shopping import close_active_browser as close_shopping_browser
from agents.research import close_active_browser as close_research_browser
from agents.calendar import close_active_browser as close_calendar_browser
from dotenv import load_dotenv
from memory import SessionMemory
import browser_manager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()

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
    except Exception as e:
        print(f"[opensight] could not save shopping memory: {e}")


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
    except Exception as e:
        print(f"[opensight] could not save conversation history: {e}")


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


def _is_garbled(text: str) -> bool:
    words = text.split()
    if text.strip().endswith("?") and len(words) < 5:
        return True
    fragments = ["can you", "try finding", "in?", "that in"]
    if sum(1 for f in fragments if f in text.lower()) >= 2:
        return True
    return False


def _has_active_shopping_context(shopping_mem: dict) -> bool:
    return bool((shopping_mem or {}).get("last_results"))


async def send_status(ws: WebSocket, agent: str, state: str, detail: str = "") -> None:
    await ws.send_text(json.dumps({
        "type": "status",
        "agent": agent,
        "state": state,
        "detail": detail,
    }))


async def run_agent(
    intent: str,
    query: str,
    history: list,
    shopping_mem: dict,
    last_intent: str = "",
    status_cb=None,
    memory=None,
) -> tuple[str, dict | None]:
    if intent == "SHOPPING":
        result = await run_shopping_agent(query, shopping_mem, memory=memory)
        if isinstance(result, tuple):
            return result
        return result, None
    elif intent == "CALENDAR":
        return await run_calendar_agent(query, memory=memory), None
    elif intent == "RESEARCH":
        return await run_research_agent(query, history, status_cb=status_cb, memory=memory), None
    else:
        return await run_general_agent(query, history, memory=memory), None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global _conversation_history, _shopping_memory, _last_intent, _session_memory

    await ws.accept()
    print("[opensight] client connected")

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            user_text = message.get("text", "")

            if _is_garbled(user_text) or (
                len(user_text.split()) < 4
                and not _is_short_actionable_text(user_text, _shopping_memory)
            ):
                await ws.send_text(json.dumps({
                    "type": "response",
                    "text": "I didn't catch that. Could you say that again?"
                }))
                await send_status(ws, "IDLE", "idle")
                continue

            print(f"[opensight] received: {user_text}")
            await send_status(ws, "BRAIN", "thinking", "routing")

            _session_memory.add_turn("user", user_text)

            try:
                # ── follow-up priority: shopping beats research ──
                # If the user has active shopping results, NEVER override to research.
                # Only fall through to research follow-up if shopping context is absent.
                shopping_followup_active = _has_active_shopping_context(_shopping_memory)

                if not shopping_followup_active and _is_followup(user_text) and research_memory["last_papers"]:
                    print(f"[opensight] research follow-up override")
                    steps = [{"intent": "RESEARCH", "query": user_text}]
                else:
                    steps = await plan_intent(
                        user_text,
                        _conversation_history,
                        memory=_session_memory,
                        shopping_memory=_shopping_memory,
                    )

                print(f"[opensight] plan: {steps}")

                all_responses = []
                previous_result = ""

                for i, step in enumerate(steps):
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

                    print(f"[opensight] step {i+1}: {intent} | query: {query}")

                    async def _research_status(msg: str):
                        try:
                            await ws.send_text(json.dumps({"type": "research_status", "text": msg}))
                        except Exception:
                            pass

                    result, memory_update = await run_agent(
                        intent, query, _conversation_history, _shopping_memory,
                        _last_intent,
                        status_cb=_research_status if intent == "RESEARCH" else None,
                        memory=_session_memory,
                    )
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
                import traceback
                traceback.print_exc()
                final_response = f"Sorry, I ran into an issue: {str(e)}"
                print(f"[opensight] error: {e}")

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