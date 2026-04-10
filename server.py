import asyncio
import sys
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.shopping import run_shopping_agent
from agents.calendar import run_calendar_agent
from agents.research import run_research_agent
from agents.router import plan_intent, generate_with_fallback
from google import genai
import os
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

AGENT_LABELS = {
    "BRAIN": "routing",
    "SHOPPING": "searching Amazon",
    "CALENDAR": "checking your calendar",
    "RESEARCH": "searching research papers",
    "GENERAL": "thinking",
}


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


async def send_status(ws: WebSocket, agent: str, state: str, detail: str = "") -> None:
    await ws.send_text(json.dumps({
        "type": "status",
        "agent": agent,
        "state": state,
        "detail": detail,
    }))


async def run_agent(intent: str, query: str, shopping_memory: dict | None = None) -> tuple[str, dict | None]:
    if intent == "SHOPPING":
        result_text, memory_update = await run_shopping_agent(query, shopping_memory)
        return result_text, memory_update
    elif intent == "CALENDAR":
        return await run_calendar_agent(query), None
    elif intent == "RESEARCH":
        return await run_research_agent(query), None
    else:
        return await generate_with_fallback(f"Answer in 2 sentences max, conversationally: {query}"), None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    print("[opensight] client connected")
    conversation_history = []  # moved outside the loop
    shopping_memory = {"last_query": "", "last_results": []}

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

            try:
                steps = await plan_intent(user_text, conversation_history, shopping_memory)
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
                    result, memory_update = await run_agent(intent, query, shopping_memory)
                    all_responses.append(result)
                    previous_result = result

                    if intent == "SHOPPING" and memory_update is not None:
                        shopping_memory = memory_update

                if len(all_responses) == 1:
                    final_response = all_responses[0]
                else:
                    combine_prompt = f"""
                    A user asked: "{user_text}"
                    These tasks were completed:
                    {chr(10).join([f"Step {i+1}: {r}" for i, r in enumerate(all_responses)])}
                    Summarize in 2-3 SHORT sentences max. spoken out loud. No lists, no bullet points.
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

            await ws.send_text(json.dumps({"type": "response", "text": final_response}))
            await send_status(ws, "IDLE", "idle")

    except WebSocketDisconnect:
        print("[opensight] client disconnected")