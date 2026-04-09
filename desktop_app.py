import asyncio
import json
import math
import os
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk
from collections import deque

import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

try:
    websockets = __import__("websockets")
except Exception:
    websockets = None

SAMPLE_RATE = 48000


class LiquidGlassDisplay:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.listening = False
        self.stop_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.listen_thread: threading.Thread | None = None
        self.session_token = 0
        self.pulse_step = 0
        self.pulse_job = None

        self.voice_queue: queue.Queue[str | None] = queue.Queue()
        self.voice_thread = threading.Thread(target=self._voice_worker, daemon=True)
        self.voice_thread.start()

        self.is_speaking = False
        self.suppress_until = 0.0
        self.sample_rate = SAMPLE_RATE
        self.transcript_history: list[str] = []
        self.live_transcript = ""
        self.max_transcript_lines = 6
        self.agent_ws_url = "ws://127.0.0.1:8080/ws"
        self.agent_enabled = websockets is not None
        self.agent_state = "idle"

        self.orb_cx = 0
        self.orb_cy = 0
        self.orb_r = 0

        # log mic on startup
        try:
            default_input_device = sd.default.device[0]
            info = sd.query_devices(default_input_device, "input")
            print(
                f"[mic] Using default input device {default_input_device}: "
                f"{info['name']} @ {int(info['default_samplerate'])}Hz"
            )
            self.sample_rate = int(info["default_samplerate"])
        except Exception as e:
            print(f"[mic] Default input device error: {e}, falling back to library default")

        self.root.title("OpenSight")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        self.root.configure(bg="#0b1826")

        try:
            self.root.attributes("-alpha", 0.90)
        except tk.TclError:
            pass

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.stage = tk.Frame(self.root, bg="#0b1826")
        self.stage.grid(sticky="nsew")
        self.stage.grid_rowconfigure(0, weight=1)
        self.stage.grid_columnconfigure(0, weight=1)

        self.bg_canvas = tk.Canvas(self.stage, bg="#0b1826", highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", self.redraw)
        self.bg_canvas.bind("<Button-1>", self.on_canvas_click)

        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    # ── drawing ──

    def redraw(self, event=None) -> None:
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        self.bg_canvas.delete("all")

        top = (229, 245, 255)
        bottom = (163, 209, 235)
        for i in range(h):
            t = i / max(h - 1, 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            self.bg_canvas.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")

        orb_r = max(24, min(36, w // 36))
        cx = w // 2
        cy = int(h * 0.46)
        self.orb_cx, self.orb_cy, self.orb_r = cx, cy, orb_r

        if self.listening:
            rings = [orb_r + 22, orb_r + 14, orb_r + 8]
            cols = ["#88cbe8", "#a7ddf2", "#c7ebf8"]
            for i, (base_r, col) in enumerate(zip(rings, cols)):
                phase = (self.pulse_step + i * 3) % 15
                rr = max(orb_r + 3, base_r - phase)
                self.bg_canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=col, outline="")
        else:
            for ring_r, col in ((orb_r + 18, "#9fd5ef"), (orb_r + 10, "#b5e0f4"), (orb_r + 4, "#caeaf8")):
                self.bg_canvas.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, fill=col, outline="")

        core_fill = "#96d2e4" if self.listening else "#e5f8ff"
        icon_col = "#245972" if self.listening else "#356985"
        self.bg_canvas.create_oval(cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r, fill=core_fill, outline="")
        self.draw_mic_icon(cx, cy, icon_col)

        status = "LISTENING" if self.listening else "IDLE"
        self.bg_canvas.create_text(cx, cy + orb_r + 24, text=status, fill="#4d7390", font=("SF Mono", 10, "bold"))
        agent_text = f"AGENT: {self.agent_state.upper()}" if self.agent_enabled else "AGENT: OFFLINE"
        self.bg_canvas.create_text(cx, cy + orb_r + 40, text=agent_text, fill="#4d7390", font=("SF Mono", 9))

        transcript_title_y = cy + orb_r + 58
        self.bg_canvas.create_text(cx, transcript_title_y, text="TRANSCRIPT", fill="#4d7390", font=("SF Mono", 9, "bold"))
        transcript_lines = self.transcript_history[-self.max_transcript_lines:]
        if self.live_transcript:
            transcript_lines = transcript_lines + [self.live_transcript]
        transcript_text = "\n".join(transcript_lines) if transcript_lines else "Speak and your words will appear here..."
        self.bg_canvas.create_text(
            cx, transcript_title_y + 18,
            text=transcript_text,
            fill="#2e5c7a" if self.transcript_history else "#5c86a1",
            font=("SF Mono", 11),
            width=int(w * 0.75),
            justify="center",
            anchor="n",
        )

    def draw_mic_icon(self, cx: int, cy: int, color: str) -> None:
        self.bg_canvas.create_oval(cx - 9, cy - 14, cx + 9, cy + 4, fill=color, outline="")
        self.bg_canvas.create_rectangle(cx - 4, cy + 1, cx + 4, cy + 14, fill=color, outline="")
        self.bg_canvas.create_arc(cx - 12, cy - 7, cx + 12, cy + 9, start=200, extent=140, style="arc", outline=color, width=2)
        self.bg_canvas.create_line(cx, cy + 14, cx, cy + 21, fill=color, width=2)
        self.bg_canvas.create_line(cx - 7, cy + 21, cx + 7, cy + 21, fill=color, width=2)

    # ── listening ──

    def on_canvas_click(self, event) -> None:
        dx = event.x - self.orb_cx
        dy = event.y - self.orb_cy
        if math.sqrt(dx * dx + dy * dy) <= self.orb_r + 18:
            self.toggle_listening()

    def toggle_listening(self) -> None:
        self.listening = not self.listening
        self.session_token += 1

        if self.listening:
            self.stop_event.clear()
            self.is_speaking = False  # fix: reset stuck speaking state
            self.suppress_until = 0.0  # fix: reset suppression
            self.agent_state = "listening"
            current_session = self.session_token
            self.listen_thread = threading.Thread(
                target=self._run_deepgram_loop,
                args=(current_session,),
                daemon=True,
            )
            self.listen_thread.start()
            self._start_pulse_loop()
        else:
            self.stop_event.set()
            self.agent_state = "idle"
            self._stop_pulse_loop()

        self.redraw()

    def _run_deepgram_loop(self, session_token: int) -> None:
        asyncio.run(self._deepgram_listen(session_token))

    async def _deepgram_listen(self, session_token: int) -> None:
        api_key = os.getenv("DEEPGRAM_API_KEY")
        if not api_key:
            self._safe_after(0, self._append_transcript, "[Deepgram API key missing in .env]")
            return

        url = (
            "wss://api.deepgram.com/v1/listen"
            "?model=nova-2"
            "&language=en-US"
            "&smart_format=true"
            "&interim_results=true"
            "&endpointing=250"
            "&encoding=linear16"
            "&channels=1"
            f"&sample_rate={self.sample_rate}"
        )
        headers = {"Authorization": f"Token {api_key}"}
        self._safe_after(0, self._append_transcript, "[Connecting to Deepgram...]")

        try:
            async with websockets.connect(
                url,
                additional_headers=headers,
                ping_interval=None,  # fix: let Deepgram manage keepalive
            ) as ws:
                self._safe_after(0, self._append_transcript, "[Deepgram connected — speak now]")
                loop = asyncio.get_running_loop()
                ws_alive = True
                audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=50)

                async def send_audio_frames() -> None:
                    while ws_alive and not self.stop_event.is_set() and session_token == self.session_token:
                        frame = await asyncio.to_thread(audio_queue.get)
                        if frame is None:
                            return
                        await ws.send(frame)

                def audio_callback(indata, frames, t, status):
                    if status:
                        print(f"[mic] callback status: {status}")
                    if not ws_alive:
                        return
                    if self.stop_event.is_set():
                        return
                    if session_token != self.session_token:
                        return
                    if self.is_speaking:
                        return
                    now = time.monotonic()
                    if now < self.suppress_until:
                        remaining = self.suppress_until - now
                        if remaining > 0.05:  # only log if meaningfully suppressed
                            print(f"[mic] suppressed for {remaining:.2f}s")
                        return
                    frame = bytes(indata)
                    try:
                        audio_queue.put_nowait(frame)
                    except queue.Full:
                        try:
                            audio_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            audio_queue.put_nowait(frame)
                        except queue.Full:
                            print("[mic] audio queue still full; dropping frame")

                stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    blocksize=4800,  # 100ms at 48kHz
                    dtype="int16",
                    channels=1,
                    callback=audio_callback,
                )
                stream.start()
                print(f"[mic] stream started at {self.sample_rate}Hz")

                sender_task = asyncio.create_task(send_audio_frames())

                try:
                    while not self.stop_event.is_set() and session_token == self.session_token:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            data = json.loads(msg)
                            msg_type = data.get("type", "")

                            if msg_type == "Results":
                                transcript = (
                                    data.get("channel", {})
                                        .get("alternatives", [{}])[0]
                                        .get("transcript", "")
                                )
                                is_final = bool(data.get("is_final") or data.get("speech_final"))
                                if transcript and transcript.strip():
                                    if is_final:
                                        print(f"[deepgram] final: {transcript}")
                                        self._safe_after(0, self._append_transcript, f"You: {transcript}")
                                        self._safe_after(0, self._set_live_transcript, "")
                                        threading.Thread(
                                            target=self._process_recognized_text,
                                            args=(transcript, session_token),
                                            daemon=True,
                                        ).start()
                                    else:
                                        print(f"[deepgram] interim: {transcript}")
                                        self._safe_after(0, self._set_live_transcript, f"... {transcript}")
                            elif msg_type == "Metadata":
                                print(f"[deepgram] metadata: {data}")
                            elif msg_type == "Error":
                                print(f"[deepgram] error msg: {data}")

                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            print(f"[deepgram] recv error: {e}")
                            break
                finally:
                    ws_alive = False
                    try:
                        audio_queue.put_nowait(None)
                    except queue.Full:
                        pass
                    sender_task.cancel()
                    stream.stop()
                    stream.close()
                    print("[mic] stream stopped")

        except Exception as e:
            self._safe_after(0, self._append_transcript, f"[Deepgram error: {e}]")
            print(f"[deepgram] connection error: {e}")

    # ── pulse animation ──

    def _start_pulse_loop(self) -> None:
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
        self._pulse_tick()

    def _stop_pulse_loop(self) -> None:
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None

    def _pulse_tick(self) -> None:
        if not self.listening:
            return
        self.pulse_step = (self.pulse_step + 1) % 30
        self.redraw()
        self.pulse_job = self.root.after(80, self._pulse_tick)

    # ── agent ──

    def _process_recognized_text(self, text: str, session_token: int) -> None:
        if session_token != self.session_token:
            return
        if len(text.split()) < 3:
            return
        if not self.agent_enabled:
            self.voice_queue.put(text)
            return

        response = self._query_agent_response(text, session_token)
        if session_token != self.session_token:
            return
        if response:
            self._safe_after(0, self._append_transcript, f"OpenSight: {response}")
            self.voice_queue.put(response)

    def _query_agent_response(self, user_text: str, session_token: int) -> str:
        if websockets is None:
            self._safe_after(0, self._set_agent_state, "offline")
            return ""
        try:
            return asyncio.run(self._query_agent_response_async(user_text, session_token))
        except Exception as e:
            print(f"[agent] query error: {e}")
            self._safe_after(0, self._set_agent_state, "offline")
            return ""

    async def _query_agent_response_async(self, user_text: str, session_token: int) -> str:
        self._safe_after(0, self._set_agent_state, "thinking")
        try:
            async with websockets.connect(self.agent_ws_url, open_timeout=5, close_timeout=1) as ws:
                await ws.send(json.dumps({"text": user_text}))
                final_response = ""

                while True:
                    if session_token != self.session_token:
                        return ""
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    payload = json.loads(raw)
                    msg_type = payload.get("type")

                    if msg_type == "status":
                        state = str(payload.get("state", "thinking")).strip() or "thinking"
                        self._safe_after(0, self._set_agent_state, state)
                    elif msg_type == "response":
                        final_response = str(payload.get("text", "")).strip()
                        break

                self._safe_after(0, self._set_agent_state, "idle")
                return final_response
        except Exception as e:
            print(f"[agent] ws error: {e}")
            self._safe_after(0, self._set_agent_state, "offline")
            return ""

    def _set_agent_state(self, state: str) -> None:
        normalized = state.strip().lower() if state else "idle"
        if normalized != self.agent_state:
            self.agent_state = normalized
            self.redraw()

    def _set_live_transcript(self, text: str) -> None:
        self.live_transcript = text.strip()
        self.redraw()

    # ── voice output ──

    def _voice_worker(self) -> None:
        while not self.shutdown_event.is_set():
            phrase = self.voice_queue.get()
            if phrase is None:
                break
            try:
                self.is_speaking = True
                self._speak_text(phrase)
            except Exception as e:
                print(f"[tts] error: {e}")
            finally:
                self.is_speaking = False
                self.suppress_until = time.monotonic() + 0.5  # fix: reduced from 1.0 to 0.5s

    def _speak_text(self, text: str) -> None:
        system_name = platform.system()
        if system_name == "Darwin":
            subprocess.run(["say", "-v", "Samantha", text], check=False)
        elif system_name == "Windows":
            safe = text.replace("'", "''")
            cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{safe}')"
            )
            subprocess.run(["powershell", "-Command", cmd], check=False)
        else:
            subprocess.run(["espeak", text], check=False)

    # ── helpers ──

    def _safe_after(self, delay_ms: int, callback, *args, **kwargs) -> None:
        try:
            if kwargs:
                self.root.after(delay_ms, lambda: callback(*args, **kwargs))
            else:
                self.root.after(delay_ms, callback, *args)
        except tk.TclError:
            pass

    def _append_transcript(self, text: str) -> None:
        cleaned = text.replace("\r", " ").replace("\n", " ").strip()
        if not cleaned:
            return
        self.transcript_history.append(cleaned)
        if len(self.transcript_history) > 80:
            self.transcript_history = self.transcript_history[-80:]
        self.redraw()

    def close_app(self) -> None:
        self.session_token += 1
        self.stop_event.set()
        self.shutdown_event.set()
        self.voice_queue.put(None)
        self._stop_pulse_loop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = LiquidGlassDisplay(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    root.mainloop()


if __name__ == "__main__":
    main()