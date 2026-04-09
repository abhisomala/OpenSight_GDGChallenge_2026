import asyncio
import json

try:
    websockets = __import__("websockets")
except Exception:
    websockets = None


def process_recognized_text(state, text: str, session_token: int, on_response_cb, safe_after_cb):
    if session_token != state.session_token:
        return
    if len(text.split()) < 3:
        return
    if not state.agent_enabled:
        state.voice_queue.put(text)
        return

    response = query_agent_response(state, text, session_token, safe_after_cb)
    if session_token != state.session_token:
        return
    if response:
        safe_after_cb(0, on_response_cb, response)
        state.voice_queue.put(response)


def query_agent_response(state, user_text: str, session_token: int, safe_after_cb) -> str:
    if websockets is None:
        return ""
    try:
        return asyncio.run(_query_agent_response_async(state, user_text, session_token, safe_after_cb))
    except Exception as e:
        print(f"[agent] query error: {e}")
        return ""


async def _query_agent_response_async(state, user_text: str, session_token: int, safe_after_cb) -> str:
    safe_after_cb(0, set_agent_status, state, "BRAIN", "thinking", "routing")
    try:
        async with websockets.connect(state.agent_ws_url, open_timeout=5, close_timeout=1) as ws:
            await ws.send(json.dumps({"text": user_text}))
            final_response = ""

            while True:
                if session_token != state.session_token:
                    return ""
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                payload = json.loads(raw)
                msg_type = payload.get("type")

                if msg_type == "status":
                    agent = str(payload.get("agent", "BRAIN")).strip() or "BRAIN"
                    s = str(payload.get("state", "thinking")).strip() or "thinking"
                    detail = str(payload.get("detail", "")).strip()
                    safe_after_cb(0, set_agent_status, state, agent, s, detail)
                elif msg_type == "response":
                    final_response = str(payload.get("text", "")).strip()
                    break

            safe_after_cb(0, set_agent_status, state, "IDLE", "idle", "")
            return final_response
    except Exception as e:
        print(f"[agent] ws error: {e}")
        safe_after_cb(0, set_agent_status, state, "IDLE", "offline", "")
        return ""


AGENT_ORDER = ["BRAIN", "SHOPPING", "CALENDAR", "RESEARCH", "GENERAL"]


def set_agent_status(state, agent: str, s: str, detail: str = "") -> None:
    normalized_agent = normalize_agent(agent)
    normalized_state = s.strip().lower() if s else "idle"
    state.agent_focus = normalized_agent
    state.agent_phase = normalized_state


def normalize_agent(agent: str) -> str:
    normalized = agent.strip().upper() if agent else "IDLE"
    if normalized in {"ROUTER", "BRAIN", "PLANNER"}:
        return "BRAIN"
    if normalized in AGENT_ORDER:
        return normalized
    if normalized in {"IDLE", "OFFLINE"}:
        return "IDLE"
    return "GENERAL"


def agent_from_detail(detail: str) -> str:
    lowered = detail.lower()
    if "amazon" in lowered or "shopping" in lowered:
        return "SHOPPING"
    if "calendar" in lowered or "schedule" in lowered:
        return "CALENDAR"
    if "research" in lowered or "paper" in lowered:
        return "RESEARCH"
    return "BRAIN"