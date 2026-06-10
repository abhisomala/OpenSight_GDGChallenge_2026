"""Shared runtime state and persisted UI preferences for OpenSight."""
import queue
import threading
import json
import os
import time

class AppState:
    """Store live app state, voice settings, and UI persistence paths."""
    def __init__(self):
        """Initialize the default application state."""
        self.listening = False
        self.stop_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.session_token = 0
        self.pulse_step = 0
        self.last_final_norm = ""
        self.last_final_ts = 0.0
        self.agent_request_in_flight = False
        self.agent_lock = threading.Lock()

        self.voice_queue: queue.Queue[str | None] = queue.Queue()

        self.is_speaking = False
        self.suppress_until = 0.0
        self.sample_rate = 48000

        self.transcript_history: list[str] = []
        self.live_transcript = ""
        self.last_user_text = ""
        self.last_ai_text = ""

        self.agent_ws_url = os.getenv(
            "OPENSIGHT_WS_URL",
            "wss://opensight-backend-348346331222.us-east1.run.app/ws"
        )
        self.agent_enabled = True
        self.agent_focus = "IDLE"
        self.agent_phase = "idle"

        self.ui_mode = "light"
        self.active_right_tab = "agents"
        self.research_panel_open = False
        self.research_history: list[str] = []
        self.username = ""
        self.ui_config_path = os.path.join(os.path.dirname(__file__), ".opensight_ui.json")

        self.reasoning_steps = [
            {"id": 1, "label": "Classify intent", "status": "pending", "summary": "Waiting for request"},
            {"id": 2, "label": "Extract constraints", "status": "pending", "summary": "Waiting for request"},
            {"id": 3, "label": "Route to agent", "status": "pending", "summary": "Waiting for request"},
            {"id": 4, "label": "Execute task", "status": "pending", "summary": "Waiting for request"},
            {"id": 5, "label": "Generate response", "status": "pending", "summary": "Waiting for request"},
        ]
        self.reasoning_transition_at = [time.monotonic()] * len(self.reasoning_steps)
        self.reasoning_active_index = -1
        self.reasoning_last_event = "idle"

        self.orb_cx = 0
        self.orb_cy = 0
        self.orb_r = 0

    def load_ui_preferences(self) -> None:
        """Load UI preferences from disk into memory."""
        try:
            with open(self.ui_config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        mode = str(data.get("ui_mode", "")).lower()
        if mode in ("light", "dark"):
            self.ui_mode = mode

        username = data.get("username", "")
        if isinstance(username, str):
            self.username = username.strip()

    def save_ui_preferences(self) -> None:
        """Save UI preferences to disk."""
        data = {
            "ui_mode": self.ui_mode,
            "username": self.username,
        }
        try:
            with open(self.ui_config_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            return