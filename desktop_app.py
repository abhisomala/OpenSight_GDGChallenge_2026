import math
import os
import threading
import time
import tkinter as tk
from dotenv import load_dotenv

from app_state import AppState
from audio_engine import init_microphone, run_deepgram_loop, voice_worker
from agent import process_recognized_text, set_agent_status, AGENT_ORDER

load_dotenv()

try:
    websockets = __import__("websockets")
except Exception:
    websockets = None


class LiquidGlassDisplay:

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.state = AppState()
        self.state.agent_enabled = websockets is not None
        self.pulse_job = None

        init_microphone(self.state)

        self.voice_thread = threading.Thread(
            target=voice_worker, args=(self.state,), daemon=True
        )
        self.voice_thread.start()

        self.root.title("OpenSight - Technology that Adapts to You.")
        self.root.geometry("720x360")
        self.root.minsize(720, 360)
        self.root.resizable(False, False)
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
        s = self.state
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        self.bg_canvas.delete("all")

        rail_w = max(224, min(252, int(w * 0.24)))
        rail_x = max(0, w - rail_w)
        main_w = max(320, rail_x)

        top = (229, 245, 255)
        bottom = (163, 209, 235)
        for i in range(h):
            t = i / max(h - 1, 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            self.bg_canvas.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")

        self.bg_canvas.create_rectangle(rail_x, 0, w, h, fill="#edf3f7", outline="")
        self.bg_canvas.create_line(rail_x, 0, rail_x, h, fill="#b7c9d6", width=2)
        self._draw_agent_rail(rail_x, w, h)

        orb_r = max(24, min(36, main_w // 28))
        cx = max(180, int(main_w * 0.50))
        cy = h - orb_r - 16
        s.orb_cx, s.orb_cy, s.orb_r = cx, cy, orb_r

        if s.listening:
            rings = [orb_r + 22, orb_r + 14, orb_r + 8]
            cols = ["#88cbe8", "#a7ddf2", "#c7ebf8"]
            for i, (base_r, col) in enumerate(zip(rings, cols)):
                phase = (s.pulse_step + i * 3) % 15
                rr = max(orb_r + 3, base_r - phase)
                self.bg_canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, fill=col, outline="")
        else:
            for ring_r, col in ((orb_r + 18, "#9fd5ef"), (orb_r + 10, "#b5e0f4"), (orb_r + 4, "#caeaf8")):
                self.bg_canvas.create_oval(cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r, fill=col, outline="")

        core_fill = "#96d2e4" if s.listening else "#e5f8ff"
        icon_col = "#245972" if s.listening else "#356985"
        self.bg_canvas.create_oval(cx - orb_r, cy - orb_r, cx + orb_r, cy + orb_r, fill=core_fill, outline="")
        self._draw_mic_icon(cx, cy, icon_col)

        status = "LISTENING" if s.listening else "IDLE"
        self.bg_canvas.create_text(cx, cy - orb_r - 18, text=status, fill="#4d7390", font=("SF Mono", 11, "bold"))

        stack_cx = max(180, int(main_w * 0.50))
        text_w = max(260, int(main_w * 0.78))
        top_zone_y = int(h * 0.18)
        divider_y = int(h * 0.45)
        bottom_zone_y = int(h * 0.62)

        self.bg_canvas.create_text(stack_cx, top_zone_y - 22, text="YOU",
                                    fill="#7aa5bc", font=("SF Mono", 8, "bold"), anchor="center")
        user_display = s.live_transcript if s.live_transcript else (
            s.last_user_text if s.last_user_text else "Speak and your words will appear here..."
        )
        self.bg_canvas.create_text(stack_cx, top_zone_y, text=user_display,
                                    fill="#2b5d79" if (s.live_transcript or s.last_user_text) else "#6a8ba2",
                                    font=("SF Mono", 12), width=text_w, justify="center", anchor="center")

        self.bg_canvas.create_line(stack_cx - 120, divider_y, stack_cx + 120, divider_y,
                                    fill="#a8c4d4", width=1, dash=(4, 4))

        self.bg_canvas.create_text(stack_cx, bottom_zone_y - 22, text="OPENSIGHT",
                                    fill="#7aa5bc", font=("SF Mono", 8, "bold"), anchor="center")
        ai_display = s.last_ai_text if s.last_ai_text else "Response will appear here..."
        self.bg_canvas.create_text(stack_cx, bottom_zone_y, text=ai_display,
                                    fill="#1a4a62" if s.last_ai_text else "#6a8ba2",
                                    font=("SF Mono", 12), width=text_w, justify="center", anchor="center")

    def _draw_mic_icon(self, cx: int, cy: int, color: str) -> None:
        self.bg_canvas.create_oval(cx - 9, cy - 14, cx + 9, cy + 4, fill=color, outline="")
        self.bg_canvas.create_rectangle(cx - 4, cy + 1, cx + 4, cy + 14, fill=color, outline="")
        self.bg_canvas.create_arc(cx - 12, cy - 7, cx + 12, cy + 9, start=200, extent=140, style="arc", outline=color, width=2)
        self.bg_canvas.create_line(cx, cy + 14, cx, cy + 21, fill=color, width=2)
        self.bg_canvas.create_line(cx - 7, cy + 21, cx + 7, cy + 21, fill=color, width=2)

    def _draw_agent_rail(self, rail_x: int, w: int, h: int) -> None:
        self.bg_canvas.create_text(rail_x + 18, 18, text="BRAIN / AGENTS",
                                    fill="#507088", font=("SF Mono", 10, "bold"), anchor="nw")
        card_left = rail_x + 14
        card_right = w - 14
        card_h = 40
        gap = 8
        start_y = 42

        for index, agent in enumerate(AGENT_ORDER):
            y_top = start_y + index * (card_h + gap)
            y_bottom = y_top + card_h
            active = agent == self.state.agent_focus
            detail = self._agent_detail(agent)
            fill, outline, title_color, detail_color, accent = self._agent_card_colors(agent, active)

            if active:
                self._rounded_rect(card_left + 2, y_top + 3, card_right + 2, y_bottom + 3,
                                   radius=12, fill="#cfdbe6", outline="")

            self._rounded_rect(card_left, y_top, card_right, y_bottom,
                               radius=12, fill=fill, outline=outline, width=1)

            dot_r = 4 if not active else 5 + (self.state.pulse_step % 4)
            dot_x = card_left + 16
            dot_y = y_top + 18
            self.bg_canvas.create_oval(dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r,
                                       fill=accent, outline="")
            self.bg_canvas.create_text(card_left + 32, y_top + 8, text=agent,
                                       fill=title_color, font=("SF Mono", 10, "bold"), anchor="nw")
            self.bg_canvas.create_text(card_left + 32, y_top + 23, text=detail,
                                       fill=detail_color, font=("SF Mono", 9), anchor="nw")

    def _agent_detail(self, agent: str) -> str:
        return {
            "BRAIN":    "routing requests",
            "SHOPPING": "scanning options",
            "CALENDAR": "checking schedules",
            "RESEARCH": "pulling sources",
            "GENERAL":  "composing responses",
        }.get(agent, "idle")

    def _rounded_rect(self, x1, y1, x2, y2, radius, *, fill, outline, width=1) -> None:
        points = [
            x1 + radius, y1, x2 - radius, y1,
            x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2,
            x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius,
            x1, y1 + radius, x1, y1,
        ]
        self.bg_canvas.create_polygon(points, smooth=True, splinesteps=24,
                                       fill=fill, outline=outline, width=width)

    def _agent_card_colors(self, agent: str, active: bool) -> tuple:
        palette = {
            "BRAIN":    ("#d8ecff", "#7cb7e6", "#214f67", "#4f7488", "#49a1e6"),
            "SHOPPING": ("#e2f5ea", "#89cfa0", "#265a3d", "#587569", "#56b97a"),
            "CALENDAR": ("#fff0d6", "#e3b15a", "#705117", "#8c7854", "#e0a238"),
            "RESEARCH": ("#e7e0ff", "#b19ae8", "#4f3e7d", "#72688f", "#8b6be8"),
            "GENERAL":  ("#e3edf4", "#9eb4c4", "#334a5d", "#63798a", "#7aa7c2"),
        }
        inactive = ("#edf1f4", "#c8d3dc", "#6d7f8d", "#8a99a5", "#a7b4bf")
        return palette.get(agent, inactive) if active else inactive

    # ── listening ──

    def on_canvas_click(self, event) -> None:
        dx = event.x - self.state.orb_cx
        dy = event.y - self.state.orb_cy
        if math.sqrt(dx * dx + dy * dy) <= self.state.orb_r + 18:
            self.toggle_listening()

    def toggle_listening(self) -> None:
        s = self.state
        s.listening = not s.listening
        s.session_token += 1

        if s.listening:
            s.stop_event.clear()
            s.is_speaking = False
            s.suppress_until = 0.0
            s.agent_focus = "BRAIN"
            s.agent_phase = "listening"
            current_session = s.session_token
            threading.Thread(
                target=run_deepgram_loop,
                args=(s, current_session, self.redraw,
                      self._on_final_transcript, self._on_interim_transcript),
                daemon=True,
            ).start()
            self._start_pulse_loop()
        else:
            s.stop_event.set()
            s.agent_focus = "IDLE"
            s.agent_phase = "idle"
            self._stop_pulse_loop()

        self.redraw()

    def _on_final_transcript(self, transcript: str) -> None:
        self._safe_after(0, self._apply_final_transcript, transcript)

    def _apply_final_transcript(self, transcript: str) -> None:
        s = self.state

        normalized = " ".join(transcript.lower().split())
        now = time.monotonic()
        if normalized == s.last_final_norm and (now - s.last_final_ts) < 0.3:
            return
        s.last_final_norm = normalized
        s.last_final_ts = now

        if s.agent_request_in_flight:
            return

        s.last_user_text = transcript
        s.live_transcript = ""
        s.transcript_history.append(f"You: {transcript}")
        self.redraw()
        threading.Thread(
            target=process_recognized_text,
            args=(s, transcript, s.session_token, self._on_ai_response, self._safe_after),
            daemon=True,
        ).start()

    def _on_interim_transcript(self, text: str) -> None:
        self._safe_after(0, self._apply_interim, text)

    def _apply_interim(self, text: str) -> None:
        self.state.live_transcript = text.strip()
        self.redraw()

    def _on_ai_response(self, response: str) -> None:
        s = self.state
        s.last_ai_text = response
        s.transcript_history.append(f"OpenSight: {response}")
        self.redraw()

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
        if not self.state.listening:
            return
        self.state.pulse_step = (self.state.pulse_step + 1) % 30
        self.redraw()
        self.pulse_job = self.root.after(80, self._pulse_tick)

    # ── helpers ──

    def _safe_after(self, delay_ms: int, callback, *args, **kwargs) -> None:
        try:
            if kwargs:
                self.root.after(delay_ms, lambda: callback(*args, **kwargs))
            else:
                self.root.after(delay_ms, callback, *args)
        except tk.TclError:
            pass

    def close_app(self) -> None:
        s = self.state
        s.session_token += 1
        s.stop_event.set()
        s.shutdown_event.set()
        s.voice_queue.put(None)
        self._stop_pulse_loop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = LiquidGlassDisplay(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    root.mainloop()


if __name__ == "__main__":
    main()