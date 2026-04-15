import asyncio
import sys
import json
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


def close_all_browsers():
    close_shopping_browser()
    close_research_browser()
    close_calendar_browser()


def _is_short_actionable_text(text: str, shopping_memory: dict) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    has_options = bool((shopping_memory or {}).get("last_results"))
    if not has_options:
        return False
    return any([
        "option" in t,
        any(word in t for word in ["first", "second", "third", "1st", "2nd", "3rd"]),
        any(word in t for word in ["open", "click", "buy", "select", "choose"]),
        "that one" in t,
        "this one" in t,
    ])


def _is_research_followup(text: str) -> bool:
    if not research_memory["last_papers"]:
        return False
    return _is_followup(text)


async def send_status(ws: WebSocket, agent: str, state: str, detail: str = "") -> None:
    await ws.send_text(json.dumps({
        "type": "status",
        "agent": agent,
        "state": state,
        "detail": detail,
    }))


async def run_agent(intent: str, query: str, history: list, shopping_memory: dict, last_intent: str = "", status_cb=None, memory=None) -> tuple[str, dict | None]:
    if last_intent and intent != last_intent:
        close_all_browsers()
    if intent == "SHOPPING":
        result = await run_shopping_agent(query, shopping_memory, memory=memory)
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
    await ws.accept()
    print("[opensight] client connected")
    conversation_history = []
    shopping_memory = {"last_query": "", "last_results": []}
    last_intent = ""
    session_memory = SessionMemory.load()

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            user_text = message.get("text", "")

            if len(user_text.split()) < 4 and not _is_short_actionable_text(user_text, shopping_memory):
                await ws.send_text(json.dumps({"type": "response", "text": "I didn't catch that. Could you say that again?"}))
                await send_status(ws, "IDLE", "idle")
                continue

            print(f"[opensight] received: {user_text}")
            await send_status(ws, "BRAIN", "thinking", "routing")

            # record user turn in shared memory before any agent runs
            session_memory.add_turn("user", user_text)

            try:
                # override router for research follow-ups so they never go to GENERAL
                if _is_research_followup(user_text):
                    print(f"[opensight] research follow-up override")
                    steps = [{"intent": "RESEARCH", "query": user_text}]
                else:
                    steps = await plan_intent(user_text, conversation_history, memory=session_memory)
                print(f"[opensight] plan: {steps}")

                all_responses = []
                previous_result = ""

                for i, step in enumerate(steps):
                    intent = step.get("intent", "GENERAL")
                    query = step.get("query", user_text)

                    if "{{PREVIOUS_RESULT}}" in query and previous_result:
                        query = query.replace("{{PREVIOUS_RESULT}}", previous_result)

                    label = AGENT_LABELS.get(intent, "thinking")
                    await send_status(ws, intent if intent in AGENT_LABELS else "GENERAL", "thinking", label)

                    print(f"[opensight] step {i+1}: {intent} | query: {query}")

                    async def _research_status(msg: str):
                        try:
                            await ws.send_text(json.dumps({"type": "research_status", "text": msg}))
                        except Exception:
                            pass

                    result, memory_update = await run_agent(
                        intent, query, conversation_history, shopping_memory,
                        last_intent,
                        status_cb=_research_status if intent == "RESEARCH" else None,
                        memory=session_memory,
                    )
                    last_intent = intent
                    all_responses.append(result)
                    previous_result = result

                    if intent == "SHOPPING" and memory_update is not None:
                        shopping_memory.update(memory_update)

                if len(all_responses) == 1:
                    final_response = all_responses[0]
                else:
                    combine_prompt = f"""
Combine these into one 2-sentence spoken response. No filler. No lists.
{chr(10).join([f"{r}" for r in all_responses])}
"""
                    final_response = await generate_with_fallback(combine_prompt)

            except Exception as e:
                import traceback
                traceback.print_exc()
                final_response = f"Sorry, I ran into an issue: {str(e)}"
                print(f"[opensight] error: {e}")

            conversation_history.append({"user": user_text, "assistant": final_response})
            if len(conversation_history) > 3:
                conversation_history.pop(0)

            # persist memory after every complete turn
            session_memory.last_query = user_text
            session_memory.save()

            await ws.send_text(json.dumps({"type": "response", "text": final_response}))
            await send_status(ws, "IDLE", "idle")

    except WebSocketDisconnect:
        print("[opensight] client disconnected")