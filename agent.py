"""WebSocket agent bridge for intent routing and spoken responses."""
import asyncio
import json

try:
    websockets = __import__("websockets")
except Exception:
    websockets = None


def process_recognized_text(state, text: str, session_token: int, on_response_cb, safe_after_cb, status_cb=None):
    """Handle recognized text and queue the assistant response."""
    if session_token != state.session_token:
        return
    if not text or not text.strip():
        return
    if not state.agent_enabled:
        state.voice_queue.put(text)
        return

    with state.agent_lock:
        if state.agent_request_in_flight:
            return
        state.agent_request_in_flight = True

    try:
        response = query_agent_response(state, text, session_token, safe_after_cb, status_cb=status_cb)
        if session_token != state.session_token:
            return
        if not response:
            state.voice_queue.put("Sorry, let me try that again.")
            response = query_agent_response(state, text, session_token, safe_after_cb, status_cb=status_cb)
            if session_token != state.session_token:
                return
        if response:
            safe_after_cb(0, on_response_cb, response)
            state.voice_queue.put(response)
    finally:
        with state.agent_lock:
            state.agent_request_in_flight = False


def query_agent_response(state, user_text: str, session_token: int, safe_after_cb, status_cb=None) -> str:
    """Request one assistant response and return it."""
    if websockets is None:
        return ""
    try:
        return asyncio.run(_query_agent_response_async(state, user_text, session_token, safe_after_cb, status_cb=status_cb))
    except Exception as e:
        print(f"[agent] query error: {e}")
        return ""


async def _query_agent_response_async(state, user_text: str, session_token: int, safe_after_cb, status_cb=None) -> str:
    """Stream WebSocket agent messages and return the final response."""
    safe_after_cb(0, set_agent_status, state, "BRAIN", "thinking", "routing")
    try:
        async with websockets.connect(state.agent_ws_url, open_timeout=5, close_timeout=1) as ws:
            await ws.send(json.dumps({"text": user_text}))
            final_response = ""
            shopping_loading_spoken = False

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
                    if (
                        not shopping_loading_spoken
                        and agent.strip().upper() == "SHOPPING"
                        and s.strip().lower() == "thinking"
                    ):
                        state.voice_queue.put("Searching Amazon now.")
                        shopping_loading_spoken = True
                elif msg_type == "research_status":
                    msg = str(payload.get("text", "")).strip()
                    if msg and status_cb:
                        safe_after_cb(0, status_cb, msg)
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
    """Update the current agent focus and phase."""
    normalized_agent = normalize_agent(agent)
    normalized_state = s.strip().lower() if s else "idle"
    state.agent_focus = normalized_agent
    state.agent_phase = normalized_state


def normalize_agent(agent: str) -> str:
    """Normalize agent labels to canonical values."""
    normalized = agent.strip().upper() if agent else "IDLE"
    if normalized in {"ROUTER", "BRAIN", "PLANNER"}:
        return "BRAIN"
    if normalized in AGENT_ORDER:
        return normalized
    if normalized in {"IDLE", "OFFLINE"}:
        return "IDLE"
    return "GENERAL"


def agent_from_detail(detail: str) -> str:
    """Infer an agent name from status detail text."""
    lowered = detail.lower()
    if "amazon" in lowered or "shopping" in lowered:
        return "SHOPPING"
    if "calendar" in lowered or "schedule" in lowered:
        return "CALENDAR"
    if "research" in lowered or "paper" in lowered:
        return "RESEARCH"
    return "BRAIN"