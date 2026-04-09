import asyncio
import sys
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.shopping import run_shopping_agent
from agents.calendar import run_calendar_agent
from agents.research import run_research_agent
from agents.router import plan_intent
from google import genai
import os
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

AGENT_LABELS = {
    "SHOPPING": "searching Amazon",
    "CALENDAR": "checking your calendar",
    "RESEARCH": "searching research papers",
    "GENERAL": "thinking",
}

async def run_agent(intent: str, query: str) -> str:
    if intent == "SHOPPING":
        return await run_shopping_agent(query)
    elif intent == "CALENDAR":
        return await run_calendar_agent(query)
    elif intent == "RESEARCH":
        return await run_research_agent(query)
    else:
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Answer in 2 sentences max, conversationally: {query}"
        )
        return resp.text.strip()

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    print("[opensight] client connected")

    try:
        while True:
            data = await ws.receive_text()
            message = json.loads(data)
            user_text = message.get("text", "")
            if len(user_text.split()) < 4:
                await ws.send_text(json.dumps({"type": "response", "text": "I didn't catch that. Could you say that again?"}))
                await ws.send_text(json.dumps({"type": "status", "state": "idle"}))
                continue
            print(f"[opensight] received: {user_text}")

            await ws.send_text(json.dumps({"type": "status", "state": "thinking"}))

            try:
                steps = await plan_intent(user_text)
                print(f"[opensight] plan: {steps}")

                all_responses = []
                previous_result = ""

                for i, step in enumerate(steps):
                    intent = step.get("intent", "GENERAL")
                    query = step.get("query", user_text)

                    # inject previous result if placeholder present
                    if "{{PREVIOUS_RESULT}}" in query and previous_result:
                        query = query.replace("{{PREVIOUS_RESULT}}", previous_result)

                    label = AGENT_LABELS.get(intent, "thinking")
                    await ws.send_text(json.dumps({
                        "type": "status",
                        "state": f"Step {i+1}/{len(steps)}: {label}"
                    }))

                    print(f"[opensight] step {i+1}: {intent} | query: {query}")
                    result = await run_agent(intent, query)
                    all_responses.append(result)
                    previous_result = result

                # combine all responses naturally if multiple steps
                if len(all_responses) == 1:
                    final_response = all_responses[0]
                else:
                    combine_prompt = f"""
                A user asked: "{user_text}"

                These tasks were completed:
                {chr(10).join([f"Step {i+1}: {r}" for i, r in enumerate(all_responses)])}

                Summarize in 2-3 SHORT sentences max. spoken out loud. No lists, no bullet points.
                """
                    combined = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=combine_prompt
                    )
                    final_response = combined.text.strip()

            except Exception as e:
                import traceback
                traceback.print_exc()
                final_response = f"Sorry, I ran into an issue: {str(e)}"
                print(f"[opensight] error: {e}")

            await ws.send_text(json.dumps({"type": "response", "text": final_response}))
            await ws.send_text(json.dumps({"type": "status", "state": "idle"}))

    except WebSocketDisconnect:
        print("[opensight] client disconnected")