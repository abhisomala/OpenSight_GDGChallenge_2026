import threading
import tkinter as tk
import platform
import queue
import subprocess
import time

import sounddevice as sd
import speech_recognition as sr


class MicCenterApp:
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
        self.recognizer = sr.Recognizer()
        self.sample_rate = 16000
        self.chunk_seconds = 2.5

        self.bg = "#07111c"
        self.panel = "#0f1a2b"
        self.panel_soft = "#142336"
        self.card_edge = "#22324a"
        self.accent = "#67e8f9"
        self.accent_soft = "#1c3346"
        self.text = "#eef4ff"
        self.muted = "#9fb2c9"

        self.root.title("OpenSight")
        self.root.configure(bg=self.bg)
        self.root.minsize(820, 560)
        self.root.geometry("940x620")

        try:
            self.root.iconphoto(False, tk.PhotoImage(width=1, height=1))
        except tk.TclError:
            pass

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.shell = tk.Frame(self.root, bg=self.bg)
        self.shell.grid(sticky="nsew")
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_columnconfigure(0, weight=1)

        self.card = tk.Frame(self.shell, bg=self.panel, highlightthickness=1, highlightbackground=self.card_edge)
        self.card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.92, relheight=0.82)

        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(2, weight=1)

        self.title_label = tk.Label(
            self.card,
            text="OpenSight",
            bg=self.panel,
            fg=self.text,
            font=("Helvetica Neue", 30, "bold"),
        )
        self.title_label.grid(row=0, column=0, pady=(26, 2))

        self.subtitle_label = tk.Label(
            self.card,
            text="Technology that Adapts to You.",
            bg=self.panel,
            fg=self.accent,
            font=("Helvetica Neue", 13),
        )
        self.subtitle_label.grid(row=1, column=0, pady=(0, 16))

        self.hero_frame = tk.Frame(self.card, bg=self.panel)
        self.hero_frame.grid(row=2, column=0, sticky="nsew", padx=28, pady=(0, 10))
        self.hero_frame.grid_columnconfigure(0, weight=1)
        self.hero_frame.grid_rowconfigure(1, weight=1)

        self.hero_copy = tk.Label(
            self.hero_frame,
            text="Cloud-backed transcription for clearer recognition.",
            bg=self.panel,
            fg=self.muted,
            font=("Helvetica Neue", 11),
        )
        self.hero_copy.grid(row=0, column=0, pady=(0, 12))

        self.canvas = tk.Canvas(self.hero_frame, width=190, height=190, bg=self.panel, highlightthickness=0)
        self.canvas.grid(row=1, column=0)
        self.canvas.bind("<Button-1>", self.toggle_listening)

        self.status_label = tk.Label(
            self.hero_frame,
            text="Idle",
            bg=self.panel,
            fg=self.text,
            font=("Helvetica Neue", 16, "bold"),
        )
        self.status_label.grid(row=2, column=0, pady=(12, 0))

        self.transcript_frame = tk.Frame(
            self.card,
            bg=self.panel_soft,
            highlightthickness=1,
            highlightbackground=self.card_edge,
        )
        self.transcript_frame.grid(row=3, column=0, sticky="ew", padx=28, pady=(6, 8))
        self.transcript_frame.grid_columnconfigure(0, weight=1)

        self.transcript_title = tk.Label(
            self.transcript_frame,
            text="Live Transcript",
            bg=self.panel_soft,
            fg=self.text,
            font=("Helvetica Neue", 13, "bold"),
        )
        self.transcript_title.grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        self.transcript_body = tk.Frame(self.transcript_frame, bg="#0b1624")
        self.transcript_body.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        self.transcript_body.grid_columnconfigure(0, weight=1)
        self.transcript_body.grid_rowconfigure(0, weight=1)

        self.transcript_scrollbar = tk.Scrollbar(self.transcript_body)
        self.transcript_scrollbar.grid(row=0, column=1, sticky="ns")

        self.transcript_text = tk.Text(
            self.transcript_body,
            height=7,
            wrap="word",
            bg="#0b1624",
            fg=self.text,
            insertbackground=self.text,
            relief="flat",
            font=("Helvetica Neue", 11),
            padx=12,
            pady=10,
            yscrollcommand=self.transcript_scrollbar.set,
        )
        self.transcript_text.grid(row=0, column=0, sticky="nsew")
        self.transcript_scrollbar.configure(command=self.transcript_text.yview)
        self.transcript_text.insert("end", "Your transcription will appear here.")
        self.transcript_text.configure(state="disabled")

        self.footer_label = tk.Label(
            self.card,
            text="Click the mic to toggle listening.",
            bg=self.panel,
            fg=self.muted,
            font=("Helvetica Neue", 9),
        )
        self.footer_label.grid(row=4, column=0, pady=(2, 16))

        self.draw_idle_state()

    def draw_idle_state(self) -> None:
        self.canvas.delete("all")
        self.canvas.create_oval(26, 26, 164, 164, fill="#0f1a2b", outline="#22344d", width=2)
        self.draw_mic_icon(95, 86, color=self.accent)
        self.canvas.create_text(95, 138, text="Tap to speak", fill=self.text, font=("Helvetica Neue", 10, "bold"))

    def draw_listening_state(self) -> None:
        self.canvas.delete("all")
        pulse_sizes = [162, 138, 114]
        pulse_colors = ["#12394a", "#15495c", "#176171"]
        offset = self.pulse_step % len(pulse_sizes)
        for index, size in enumerate(pulse_sizes):
            adjusted = pulse_sizes[(index + offset) % len(pulse_sizes)]
            color = pulse_colors[(index + offset) % len(pulse_colors)]
            inset = (190 - adjusted) // 2
            self.canvas.create_oval(inset, inset, 190 - inset, 190 - inset, fill=color, outline="")
        self.canvas.create_oval(30, 30, 160, 160, fill="#0a1f24", outline="#2a7f8f", width=2)
        self.draw_mic_icon(95, 86, color="#8af7ff")
        self.canvas.create_text(95, 138, text="Listening...", fill="#d8fbff", font=("Helvetica Neue", 10, "bold"))
        self.pulse_step += 1
        self.pulse_job = self.root.after(220, self.draw_listening_state)

    def draw_mic_icon(self, center_x: int, center_y: int, color: str) -> None:
        self.canvas.create_oval(center_x - 22, center_y - 30, center_x + 22, center_y + 12, fill=color, outline="")
        self.canvas.create_rectangle(center_x - 10, center_y + 2, center_x + 10, center_y + 34, fill=color, outline="")
        self.canvas.create_arc(center_x - 28, center_y - 16, center_x + 28, center_y + 22, start=200, extent=140, style="arc", outline=color, width=4)
        self.canvas.create_line(center_x, center_y + 34, center_x, center_y + 50, fill=color, width=5)
        self.canvas.create_line(center_x - 18, center_y + 50, center_x + 18, center_y + 50, fill=color, width=5)

    def toggle_listening(self, event=None) -> None:
        self.listening = not self.listening
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None
        if self.listening:
            self.status_label.configure(text="Listening")
            self.session_token += 1
            current_session = self.session_token
            self._set_transcript_text("")
            self._append_transcript("Listening for speech...")
            self.stop_event.clear()
            self.listen_thread = threading.Thread(
                target=self.capture_transcription_loop,
                args=(current_session,),
                daemon=True,
            )
            self.listen_thread.start()
            self.draw_listening_state()
        else:
            self.status_label.configure(text="Idle")
            self.session_token += 1
            self.stop_event.set()
            self.draw_idle_state()

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

                if abs(audio).mean() < 180:
                    continue

                audio_data = sr.AudioData(audio.tobytes(), self.sample_rate, 2)
                self._recognise(audio_data, session_token)
            except Exception as exc:
                self._safe_after(0, self._append_transcript, f"[Listen error: {exc}]\n")
                self._safe_after(0, self._stop_listening_from_worker)
                break

    def _recognise(self, audio: sr.AudioData, session_token: int) -> None:
        """Run primary cloud speech recognition with offline fallback."""
        if session_token != self.session_token:
            return
        try:
            text = self.recognizer.recognize_google(audio)
            cleaned = text.strip()
            if cleaned:
                self._safe_after(0, self._append_transcript, cleaned)
                self.voice_queue.put(cleaned)
        except sr.UnknownValueError:
            pass  # Silence / unintelligible — ignore
        except sr.RequestError:
            try:
                text = self.recognizer.recognize_sphinx(audio)
                cleaned = text.strip()
                if cleaned:
                    self._safe_after(0, self._append_transcript, cleaned)
                    self.voice_queue.put(cleaned)
            except sr.UnknownValueError:
                pass
            except sr.RequestError as exc:
                self._safe_after(0, self._append_transcript, f"[Speech engine error: {exc}]")
        except Exception as exc:
            self._safe_after(0, self._append_transcript, f"[Speech error: {exc}]")

    def _safe_after(self, delay_ms: int, callback, *args) -> None:
        try:
            self.root.after(delay_ms, callback, *args)
        except tk.TclError:
            pass

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
                self.suppress_until = time.monotonic() + 1.0

    def _speak_text(self, text: str) -> None:
        system_name = platform.system()
        if system_name == "Darwin":
            subprocess.run(["say", text], check=False)
        elif system_name == "Windows":
            safe_text = text.replace("'", "''")
            cmd = (
                "Add-Type -AssemblyName System.Speech; "
                "$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$speak.Speak('{safe_text}')"
            )
            subprocess.run(["powershell", "-Command", cmd], check=False)
        else:
            subprocess.run(["espeak", text], check=False)

    def _stop_listening_from_worker(self) -> None:
        self.session_token += 1
        self.stop_event.set()
        if self.listening:
            self.listening = False
            self.status_label.configure(text="Idle")
            if self.pulse_job is not None:
                self.root.after_cancel(self.pulse_job)
                self.pulse_job = None
            self.draw_idle_state()

    def _set_transcript_text(self, text: str) -> None:
        self.transcript_text.configure(state="normal")
        self.transcript_text.delete("1.0", "end")
        self.transcript_text.insert("end", text)
        self.transcript_text.configure(state="disabled")

    def _append_transcript(self, text: str) -> None:
        self.transcript_text.configure(state="normal")
        current = self.transcript_text.get("1.0", "end-1c")
        cleaned_text = text.replace("\r", " ").replace("\n", " ").strip()
        if not cleaned_text:
            self.transcript_text.configure(state="disabled")
            return
        if current and not current.endswith(" "):
            self.transcript_text.insert("end", " ")
        self.transcript_text.insert("end", cleaned_text)
        self.transcript_text.see("end")
        self.transcript_text.configure(state="disabled")

    def close_app(self) -> None:
        self.session_token += 1
        self.stop_event.set()
        self.shutdown_event.set()
        self.voice_queue.put(None)
        if self.pulse_job is not None:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    root = tk.Tk()
    app = MicCenterApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    app.run()


if __name__ == "__main__":
    main()