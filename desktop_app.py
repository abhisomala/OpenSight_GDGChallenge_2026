import math
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk

import sounddevice as sd
import speech_recognition as sr


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

        self.recognize_queue: queue.Queue[tuple[sr.AudioData, int] | None] = queue.Queue()
        self.recognize_thread = threading.Thread(target=self._recognize_worker, daemon=True)
        self.recognize_thread.start()

        self.is_speaking = False
        self.suppress_until = 0.0
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 0.8
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.sample_rate = 16000
        self.chunk_seconds = 2.0
        self.language = "en-US"
        self.min_confidence = 0.55
        self.transcript_history: list[str] = []
        self.max_transcript_lines = 6

        self.orb_cx = 0
        self.orb_cy = 0
        self.orb_r = 0

        self.root.title("Liquid Glass Display")
        self.root.geometry("1200x800")  # 24:16 aspect ratio
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

    def redraw(self, event=None) -> None:
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        self.bg_canvas.delete("all")

        # Single light one-hue gradient background (no box, no borders)
        top = (229, 245, 255)
        bottom = (163, 209, 235)
        for i in range(h):
            t = i / max(h - 1, 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.bg_canvas.create_line(0, i, w, i, fill=color)

        # Center microphone orb
        orb_r = max(24, min(36, w // 36))
        cx = w // 2
        cy = int(h * 0.46)
        self.orb_cx, self.orb_cy, self.orb_r = cx, cy, orb_r

        if self.listening:
            # animated rings when listening
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

        # Live transcript text below mic (no panel box)
        transcript_title_y = cy + orb_r + 52
        self.bg_canvas.create_text(
            cx,
            transcript_title_y,
            text="TRANSCRIPT",
            fill="#4d7390",
            font=("SF Mono", 9, "bold"),
        )
        transcript_text = "\n".join(self.transcript_history[-self.max_transcript_lines:])
        if not transcript_text:
            transcript_text = "Speak and your words will appear here..."
        self.bg_canvas.create_text(
            cx,
            transcript_title_y + 18,
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
            current_session = self.session_token
            self.listen_thread = threading.Thread(
                target=self.capture_transcription_loop,
                args=(current_session,),
                daemon=True,
            )
            self.listen_thread.start()
            self._start_pulse_loop()
        else:
            self.stop_event.set()
            self._stop_pulse_loop()

        self.redraw()

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

    def capture_transcription_loop(self, session_token: int) -> None:
        while not self.stop_event.is_set() and session_token == self.session_token:
            try:
                audio = sd.rec(
                    int(self.chunk_seconds * self.sample_rate),
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                )
                sd.wait()

                if self.stop_event.is_set() or session_token != self.session_token:
                    break
                if self.is_speaking or time.monotonic() < self.suppress_until:
                    continue

                if float(abs(audio).mean()) < 120.0:
                    continue

                audio_data = sr.AudioData(audio.tobytes(), self.sample_rate, 2)
                self.recognize_queue.put((audio_data, session_token))
            except Exception:
                break

    def _recognize_worker(self) -> None:
        while not self.shutdown_event.is_set():
            item = self.recognize_queue.get()
            if item is None:
                break
            audio, session_token = item
            self._recognise(audio, session_token)

    def _recognise(self, audio: sr.AudioData, session_token: int) -> None:
        if session_token != self.session_token:
            return
        try:
            result = self.recognizer.recognize_google(audio, language=self.language, show_all=True)
            cleaned = self._extract_best_transcript(result)
            if cleaned:
                self._safe_after(0, self._append_transcript, cleaned)
                self.voice_queue.put(cleaned)
        except sr.UnknownValueError:
            pass
        except sr.RequestError:
            pass
        except Exception:
            pass

    def _extract_best_transcript(self, result) -> str:
        if not isinstance(result, dict):
            return ""
        alternatives = result.get("alternative", [])
        if not alternatives:
            return ""

        best_text = ""
        best_score = -1.0
        for alt in alternatives:
            transcript = alt.get("transcript", "").strip()
            if not transcript:
                continue
            confidence = float(alt.get("confidence", 0.0))
            score = confidence if confidence > 0 else 0.3
            if score > best_score and (confidence == 0.0 or confidence >= self.min_confidence):
                best_text = transcript
                best_score = score
        return best_text or alternatives[0].get("transcript", "").strip()

    def _voice_worker(self) -> None:
        while not self.shutdown_event.is_set():
            phrase = self.voice_queue.get()
            if phrase is None:
                break
            try:
                self.is_speaking = True
                self._speak_text(phrase)
            except Exception:
                pass
            finally:
                self.is_speaking = False
                self.suppress_until = time.monotonic() + 0.5

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
        # Keep recent transcript bounded.
        if len(self.transcript_history) > 80:
            self.transcript_history = self.transcript_history[-80:]
        self.redraw()

    def close_app(self) -> None:
        self.session_token += 1
        self.stop_event.set()
        self.shutdown_event.set()
        self.voice_queue.put(None)
        self.recognize_queue.put(None)
        self._stop_pulse_loop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = LiquidGlassDisplay(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    root.mainloop()


if __name__ == "__main__":
    main()
