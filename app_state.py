import queue
import threading

class AppState:
    def __init__(self):
        self.listening = False
        self.stop_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.session_token = 0
        self.pulse_step = 0

        self.voice_queue: queue.Queue[str | None] = queue.Queue()

        self.is_speaking = False
        self.barge_in_event = threading.Event()
        self.suppress_until = 0.0
        self.sample_rate = 48000

        self.transcript_history: list[str] = []
        self.live_transcript = ""
        self.last_user_text = ""
        self.last_ai_text = ""

        self.agent_ws_url = "ws://127.0.0.1:8080/ws"
        self.agent_enabled = True
        self.agent_focus = "IDLE"
        self.agent_phase = "idle"

        self.orb_cx = 0
        self.orb_cy = 0
        self.orb_r = 0