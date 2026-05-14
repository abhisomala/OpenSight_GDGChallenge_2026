import math
import os
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import random
import datetime
from dotenv import load_dotenv

from app_state import AppState
from audio_engine import init_microphone, run_deepgram_loop, run_wake_word_loop, voice_worker
from agent import process_recognized_text, set_agent_status, AGENT_ORDER

from ui.ui_theme import ThemeMixin
from ui.ui_draw import DrawMixin
from ui.ui_context import ContextMixin
from ui.ui_animations import AnimationMixin

import browser_manager

load_dotenv()

try:
    websockets = __import__("websockets")
except Exception:
    websockets = None


class LiquidGlassDisplay(ThemeMixin, DrawMixin, ContextMixin, AnimationMixin):

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.state = AppState()
        self.state.load_ui_preferences()
        self.state.agent_enabled = websockets is not None

        self.pulse_job = None
        self.ai_animation_job = None
        self.thinking_job = None
        self.waveform_job = None
        self.gradient_job = None
        self.mic_level_job = None
        self.toggle_anim_job = None
        self.context_anim_job = None
        self._cursor_job = None

        self.thinking_step = 0
        self.ai_render_text = ""
        self.ai_animation_target = ""
        self.ai_animation_index = 0
        self.is_thinking = False
        self.is_speaking_visual = False
        self._cursor_visible = True
        self.research_status = ""

        self.waveform_bars = [0.28, 0.42, 0.6, 0.42, 0.28]
        self.waveform_phase = 0.0
        self.waveform_mode = "off"
        self.waveform_amp = 0.14
        self.waveform_amp_target = 0.14
        self.waveform_speed = 0.22
        self.waveform_speed_target = 0.22
        self.waveform_noise = [random.uniform(-0.03, 0.03) for _ in range(5)]
        self.gradient_phase = 0.0

        self.agent_flash: dict[str, int] = {}
        self.mic_level_smooth = 0.0
        self.user_timestamp = ""
        self.ai_timestamp = ""
        self.toggle_knob_pos: dict[str, float] = {}
        self.tab_hitboxes: dict[str, tuple] = {}
        self.agent_hitboxes: dict[str, tuple] = {}
        self.theme_toggle_hitbox = None
        self.speed_hitboxes: dict[str, tuple] = {}
        self.agent_toggle_hitboxes: dict[str, tuple] = {}
        self.clear_history_hitbox = None
        self.context_section_hitboxes: dict[str, tuple] = {}
        self.context_open_section = "about"
        self.context_documents: list[dict[str, str]] = []
        self.context_add_hitbox = None
        self.context_doc_delete_hitboxes: dict[int, tuple] = {}
        self.context_clear_docs_hitbox = None
        self.context_doc_title_entry: tk.Entry | None = None
        self.context_doc_note_entry: tk.Entry | None = None
        self.context_section_anim: dict[str, float] = {"about": 0.0, "recent": 0.0, "documents": 0.0}
        self.context_doc_hover_idx: int = -1
        self.context_doc_card_hitboxes: dict[int, tuple] = {}
        self.pill_remove_hitboxes: dict[tuple, tuple] = {}
        self.reasoning_row_hitboxes: list[tuple[int, int, int, int]] = []
        self.reasoning_hover_index = -1
        self.username_entry: tk.Entry | None = None
        self.username_window_id = None
        self.voice_speed = getattr(self.state, "voice_speed", "normal")
        self.disabled_agents: set[str] = getattr(self.state, "disabled_agents", set())
        self._last_agent_status = (self.state.agent_focus, self.state.agent_phase)
        self._reasoning_initialized_for_turn = False
        self.window_icon_tk = None
        self.logo_tk = None

        self.motion = {
            "toggle_ms": 16, "typing_ms": 22, "typing_step": 3, "typing_pause_ms": 54,
            "waveform_ms": 42, "gradient_ms": 66, "mic_ms": 72, "pulse_ms": 72,
            "thinking_ms": 360, "agent_flash_ms": 72,
        }

        for agent in AGENT_ORDER:
            self.toggle_knob_pos[agent] = 0.0 if agent in self.disabled_agents else 1.0

        init_microphone(self.state)
        self.voice_thread = threading.Thread(target=voice_worker, args=(self.state,), daemon=True)
        self.voice_thread.start()
        run_wake_word_loop(self.state, self._on_wake)

        self.root.title("OpenSight")
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenSight.DesktopApp")
            except Exception as e:
                print(f"[icon] could not set AppUserModelID: {e}")
        try:
            from PIL import Image, ImageTk
            base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_png_path = os.path.join(base_dir, "assets", "icons", "opensight_icon.png")
            ico_path = os.path.join(base_dir, "assets", "icons", "opensight_icon.ico")
            img = Image.open(icon_png_path)
            self.window_icon_tk = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self.window_icon_tk)
            self.root.after(0, lambda: self.root.iconphoto(True, self.window_icon_tk))
            if os.name == "nt":
                try:
                    img.convert("RGBA").save(ico_path, format="ICO",
                                             sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
                    self.root.iconbitmap(default=ico_path)
                    self.root.wm_iconbitmap(ico_path)
                except Exception as e:
                    print(f"[icon] could not set iconbitmap: {e}")
            self.logo_tk = ImageTk.PhotoImage(img.resize((36, 36), Image.LANCZOS))
        except Exception as e:
            print(f"[icon] could not load: {e}")

        self.root.geometry("1100x700")
        self.root.minsize(1100, 700)
        self.root.resizable(False, False)
        self.root.configure(bg=self._theme()["background"])
        try:
            self.root.attributes("-alpha", 0.95)
        except tk.TclError:
            pass

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.stage = tk.Frame(self.root, bg=self._theme()["background"])
        self.stage.grid(sticky="nsew")
        self.stage.grid_rowconfigure(0, weight=1)
        self.stage.grid_columnconfigure(0, weight=1)

        self.bg_canvas = tk.Canvas(self.stage, bg=self._theme()["background"], highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", self.redraw)
        self.bg_canvas.bind("<Button-1>", self.on_canvas_click)
        self.bg_canvas.bind("<Motion>", self.on_canvas_motion)
        self._init_typography()
        self.root.bind("<KeyPress-space>", self._on_spacebar_press)
        self.root.focus_set()
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self._start_gradient_loop()
        self._start_mic_level_loop()

        # Register our HWND with browser_manager after the window is fully rendered.
        # Delayed 500ms to ensure the window title "OpenSight" is set before lookup.
        self.root.after(500, self._register_hwnd)

    def _register_hwnd(self):
        """Tell browser_manager our real Win32 HWND so it can focus us on wake word.

        winfo_id() on Windows returns Tkinter's internal widget handle, NOT the
        Win32 HWND that SetForegroundWindow expects — focus silently failed with
        that value. FindWindowW looks up the window by its title string instead,
        which reliably returns the correct Win32 HWND.
        """
        if os.name != "nt":
            return
        try:
            import ctypes
            # Find the Win32 HWND by the window title set above ("OpenSight").
            hwnd = ctypes.windll.user32.FindWindowW(None, "OpenSight")
            if hwnd:
                browser_manager.set_opensight_hwnd(hwnd)
            else:
                print("[focus] FindWindowW returned 0 — focus may not work")
        except Exception as e:
            print(f"[focus] could not register HWND: {e}")

    def _focus_self(self):
        """Bring OpenSight to the foreground."""
        try:
            browser_manager.focus_opensight()
        except Exception:
            pass
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _init_typography(self):
        families = set(tkfont.families(self.root))
        self.font_ui = "Inter" if "Inter" in families else "Helvetica"
        self.font_mono = next(
            (f for f in ["JetBrains Mono", "SF Mono", "Menlo"] if f in families),
            "Menlo"
        )
        def sz(v): return max(8, int(round(v - 1.5)))
        self.typo = {
            "display":    (self.font_ui,   sz(30), "bold"),
            "section":    (self.font_ui,   sz(12), "bold"),
            "label":      (self.font_ui,   sz(11), "bold"),
            "label_soft": (self.font_ui,   sz(11), "normal"),
            "body":       (self.font_ui,   sz(14), "normal"),
            "body_large": (self.font_ui,   sz(15), "normal"),
            "micro":      (self.font_ui,   sz(11), "normal"),
            "mono_label": (self.font_mono, sz(11), "bold"),
            "mono_body":  (self.font_mono, sz(11), "normal"),
            "mono_micro": (self.font_mono, sz(10), "normal"),
            "mono_tiny":  (self.font_mono, sz(10), "normal"),
            "fx_large":   (self.font_ui,   sz(20), "bold"),
        }

    # ── event handlers ──

    def _on_spacebar_press(self, event):
        if not self.state.listening:
            self.toggle_listening()
        return "break"

    def _on_wake(self):
        self._safe_after(0, self._handle_wake)

    def _handle_wake(self):
        self._focus_self()
        if not self.state.listening:
            self.toggle_listening()
        self.state.voice_queue.put("Yes?")

    def on_canvas_motion(self, event):
        if self.state.active_right_tab == "agents":
            new_hover = -1
            for idx, box in enumerate(self.reasoning_row_hitboxes):
                if self._point_in_box(event.x, event.y, box):
                    new_hover = idx
                    break
            if new_hover != self.reasoning_hover_index:
                self.reasoning_hover_index = new_hover
                self.redraw()
        else:
            if self.reasoning_hover_index != -1:
                self.reasoning_hover_index = -1
                self.redraw()

        if self.state.active_right_tab == "context" and self.context_open_section == "documents":
            new_doc_hover = -1
            for doc_idx, box in self.context_doc_card_hitboxes.items():
                if self._point_in_box(event.x, event.y, box):
                    new_doc_hover = doc_idx
                    break
            if new_doc_hover != self.context_doc_hover_idx:
                self.context_doc_hover_idx = new_doc_hover
                self.redraw()

    def on_canvas_click(self, event):
        dx = event.x - self.state.orb_cx
        dy = event.y - self.state.orb_cy
        if math.sqrt(dx*dx + dy*dy) <= self.state.orb_r + 18:
            self.toggle_listening()
            return

        for tab_name, bbox in self.tab_hitboxes.items():
            if self._point_in_box(event.x, event.y, bbox):
                self.state.active_right_tab = tab_name
                self.redraw()
                return

        if self.state.active_right_tab == "settings":
            if self.theme_toggle_hitbox and self._point_in_box(event.x, event.y, self.theme_toggle_hitbox):
                self._toggle_mode()
                return
            for spd, bbox in self.speed_hitboxes.items():
                if self._point_in_box(event.x, event.y, bbox):
                    self.voice_speed = spd
                    self.state.voice_speed = spd
                    self.redraw()
                    return
            for agent, bbox in self.agent_toggle_hitboxes.items():
                if self._point_in_box(event.x, event.y, bbox):
                    self._toggle_agent(agent)
                    return
            if self.clear_history_hitbox and self._point_in_box(event.x, event.y, self.clear_history_hitbox):
                self._clear_history()
                return
            return

        if self.state.active_right_tab == "context":
            for (kind, value), bbox in list(getattr(self, "pill_remove_hitboxes", {}).items()):
                if self._point_in_box(event.x, event.y, bbox):
                    self.remove_learned_item(kind, value)
                    return
            if self.context_add_hitbox and self._point_in_box(event.x, event.y, self.context_add_hitbox):
                self._add_context_document_from_inputs()
                return
            if self.context_clear_docs_hitbox and self._point_in_box(event.x, event.y, self.context_clear_docs_hitbox):
                self._clear_context_documents()
                return
            for doc_idx, bbox in self.context_doc_delete_hitboxes.items():
                if self._point_in_box(event.x, event.y, bbox):
                    self._delete_context_document(doc_idx)
                    return
            for section, bbox in self.context_section_hitboxes.items():
                if self._point_in_box(event.x, event.y, bbox):
                    if self.context_open_section != section:
                        self.context_open_section = section
                        if self.context_anim_job:
                            self.root.after_cancel(self.context_anim_job)
                        self._tick_context_section_anim()
                    return
            return

        for agent, bbox in self.agent_hitboxes.items():
            if self._point_in_box(event.x, event.y, bbox):
                self.state.agent_focus = agent
                self.state.research_panel_open = (
                    not self.state.research_panel_open if agent == "RESEARCH" else False)
                self.redraw()
                return

    # ── agent toggle ──

    def _toggle_agent(self, agent):
        if agent in self.disabled_agents:
            self.disabled_agents.discard(agent)
            target = 1.0
        else:
            self.disabled_agents.add(agent)
            target = 0.0
        self.state.disabled_agents = self.disabled_agents
        self._animate_toggle(agent, target)

    def _animate_toggle(self, agent, target):
        current = self.toggle_knob_pos.get(agent, target)
        diff = target - current
        if abs(diff) < 0.02:
            self.toggle_knob_pos[agent] = target
            self.redraw()
            return
        self.toggle_knob_pos[agent] = current + diff * 0.20
        self.redraw()
        self.toggle_anim_job = self.root.after(self.motion["toggle_ms"], lambda: self._animate_toggle(agent, target))

    # ── history ──

    def _clear_history(self):
        self.state.transcript_history = []
        self.state.research_history = []
        self.context_documents = []
        if self.context_doc_title_entry:
            self.context_doc_title_entry.delete(0, tk.END)
        if self.context_doc_note_entry:
            self.context_doc_note_entry.delete(0, tk.END)
        self.state.last_user_text = ""
        self.state.last_ai_text = ""
        self.ai_render_text = ""
        self.ai_animation_target = ""
        self.ai_animation_index = 0
        self.user_timestamp = ""
        self.ai_timestamp = ""
        self._reset_reasoning_chain()
        self._reasoning_initialized_for_turn = False
        self.redraw()

    # ── listening ──

    def toggle_listening(self):
        s = self.state
        s.listening = not s.listening
        s.session_token += 1
        if s.listening:
            self._focus_self()
            s.stop_event.clear()
            s.is_speaking = False
            s.suppress_until = 0.0
            s.agent_focus = "BRAIN"
            s.agent_phase = "listening"
            threading.Thread(target=run_deepgram_loop,
                             args=(s, s.session_token, self.redraw,
                                   self._on_final_transcript, self._on_interim_transcript),
                             daemon=True).start()
            self.waveform_mode = "idle"
            self.waveform_amp_target = 0.24
            self.waveform_speed_target = 0.22
            self._tick_waveform()
            self._reset_reasoning_chain()
            self._reasoning_initialized_for_turn = False
            self._start_pulse_loop()
        else:
            s.stop_event.set()
            s.agent_focus = "IDLE"
            s.agent_phase = "idle"
            self.mic_level_smooth = 0.0
            self.state.reasoning_active_index = -1
            self.waveform_mode = "off"
            self._stop_pulse_loop()
        self.redraw()

    def _on_final_transcript(self, transcript):
        self._safe_after(0, self._apply_final_transcript, transcript)

    def _apply_final_transcript(self, transcript):
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
        self.user_timestamp = datetime.datetime.now().strftime("%#I:%M %p")
        self._reset_reasoning_chain()
        self._reasoning_initialized_for_turn = True
        self._activate_reasoning_step(0, summary="Classifying user intent")
        self._start_thinking()
        self.redraw()
        threading.Thread(target=process_recognized_text,
                         args=(s, transcript, s.session_token, self._on_ai_response, self._safe_after),
                         daemon=True).start()

    def _on_interim_transcript(self, text):
        self._safe_after(0, self._apply_interim, text)

    def _apply_interim(self, text):
        self.state.live_transcript = text.strip()
        self.redraw()

    def _on_ai_response(self, response):
        s = self.state
        s.last_ai_text = response
        if s.agent_focus == "RESEARCH":
            title = self._extract_research_title(response, s.last_user_text)
            if title and (not s.research_history or s.research_history[-1] != title):
                s.research_history.append(title)
        s.transcript_history.append(f"OpenSight: {response}")
        self.ai_timestamp = datetime.datetime.now().strftime("%#I:%M %p")
        self._complete_reasoning_step(3, summary="Execution finished")
        self._activate_reasoning_step(4, summary="Drafting final response")
        self._stop_thinking()
        self._start_ai_response_animation(response)
        self._safe_after(0, self._start_speaking_visual)
        self.redraw()

    def _on_research_status(self, status: str) -> None:
        self._safe_after(0, self._apply_research_status, status)

    def _apply_research_status(self, status: str) -> None:
        self.research_status = status
        self.redraw()

    # ── helpers ──

    def _point_in_box(self, x, y, box):
        x1, y1, x2, y2 = box
        return x1 <= x <= x2 and y1 <= y <= y2

    def _toggle_mode(self):
        self.state.ui_mode = "dark" if self.state.ui_mode == "light" else "light"
        self.state.save_ui_preferences()
        self.redraw()

    def _commit_username(self, event=None):
        if self.username_entry is None:
            return "break"
        self.state.username = self.username_entry.get().strip()
        self.state.save_ui_preferences()
        self.redraw()
        return "break" if event is not None else None

    def _safe_after(self, delay_ms, callback, *args, **kwargs):
        try:
            if kwargs:
                self.root.after(delay_ms, lambda: callback(*args, **kwargs))
            else:
                self.root.after(delay_ms, callback, *args)
        except tk.TclError:
            pass

    def close_app(self):
        self._commit_username()
        self._destroy_username_entry()
        self._destroy_context_doc_inputs()
        self._stop_thinking()
        self._stop_speaking_visual()
        for job in [self.ai_animation_job, self.gradient_job, self.mic_level_job,
                    self.toggle_anim_job, self.context_anim_job, self._cursor_job]:
            if job:
                self.root.after_cancel(job)
        s = self.state
        s.session_token += 1
        s.stop_event.set()
        s.shutdown_event.set()
        s.voice_queue.put(None)
        self._stop_pulse_loop()
        self.root.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenSight.DesktopApp")
        except Exception as e:
            print(f"[icon] could not set AppUserModelID: {e}")
    root = tk.Tk()
    app = LiquidGlassDisplay(root)
    root.protocol("WM_DELETE_WINDOW", app.close_app)
    root.mainloop()


if __name__ == "__main__":
    main()