import math
import os
import re
import threading
import textwrap
import time
import tkinter as tk
import tkinter.font as tkfont
import random
import datetime
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
        self.state.load_ui_preferences()
        self.state.agent_enabled = websockets is not None
        self.pulse_job = None
        self.ai_animation_job = None
        self.thinking_job = None
        self.waveform_job = None
        self.gradient_job = None
        self.mic_level_job = None
        self.toggle_anim_job = None
        self.thinking_step = 0
        self.ai_render_text = ""
        self.ai_animation_target = ""
        self.ai_animation_index = 0
        self.is_thinking = False
        self.is_speaking_visual = False
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
        # smooth toggle knob positions: agent -> 0.0 (off) to 1.0 (on)
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
        self.reasoning_row_hitboxes: list[tuple[int, int, int, int]] = []
        self.reasoning_hover_index = -1
        self.username_entry: tk.Entry | None = None
        self.username_window_id = None
        self.voice_speed = getattr(self.state, "voice_speed", "normal")
        self.disabled_agents: set[str] = getattr(self.state, "disabled_agents", set())
        self._last_agent_status = (self.state.agent_focus, self.state.agent_phase)
        self._reasoning_initialized_for_turn = False
        self.research_status = ""
        self.window_icon_tk = None
        self.logo_tk = None

        # init toggle positions
        for agent in AGENT_ORDER:
            self.toggle_knob_pos[agent] = 0.0 if agent in self.disabled_agents else 1.0

        init_microphone(self.state)
        self.voice_thread = threading.Thread(target=voice_worker, args=(self.state,), daemon=True)
        self.voice_thread.start()

        self.root.title("OpenSight - Technology that Adapts to You.")
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenSight.DesktopApp")
            except Exception as e:
                print(f"[icon] could not set AppUserModelID: {e}")
        try:
            from PIL import Image, ImageTk
            base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_png_path = os.path.join(base_dir, "opensight_icon.png")
            ico_path = os.path.join(base_dir, "opensight_icon.ico")
            img = Image.open(icon_png_path)
            self.window_icon_tk = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, self.window_icon_tk)
            self.root.after(0, lambda: self.root.iconphoto(True, self.window_icon_tk))

            if os.name == "nt":
                try:
                    img.convert("RGBA").save(
                        ico_path,
                        format="ICO",
                        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
                    )
                    self.root.iconbitmap(default=ico_path)
                    self.root.wm_iconbitmap(ico_path)
                except Exception as e:
                    print(f"[icon] could not set iconbitmap: {e}")

            logo_img = img.resize((36, 36), Image.LANCZOS)
            self.logo_tk = ImageTk.PhotoImage(logo_img)
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

    def _init_typography(self):
        families = set(tkfont.families(self.root))
        self.font_ui = "Inter" if "Inter" in families else "Helvetica"
        if "JetBrains Mono" in families:
            self.font_mono = "JetBrains Mono"
        elif "SF Mono" in families:
            self.font_mono = "SF Mono"
        else:
            self.font_mono = "Menlo"

        def sz(value: float) -> int:
            return max(8, int(round(value - 1.5)))

        self.typo = {
            "display": (self.font_ui, sz(30), "bold"),
            "section": (self.font_ui, sz(12), "bold"),
            "label": (self.font_ui, sz(11), "bold"),
            "label_soft": (self.font_ui, sz(11), "normal"),
            "body": (self.font_ui, sz(14), "normal"),
            "body_large": (self.font_ui, sz(15), "normal"),
            "micro": (self.font_ui, sz(11), "normal"),
            "mono_label": (self.font_mono, sz(11), "bold"),
            "mono_body": (self.font_mono, sz(11), "normal"),
            "mono_micro": (self.font_mono, sz(10), "normal"),
            "mono_tiny": (self.font_mono, sz(10), "normal"),
            "fx_large": (self.font_ui, sz(20), "bold"),
        }

    def _caps(self, text):
        return str(text).upper()

    # ── theme ──

    def _theme(self) -> dict:
        if self.state.ui_mode == "dark":
            return {
                "background": "#0b1826", "rail": "#111f2e", "rail_border": "#1e3347",
                "text_primary": "#EAF2FF", "text_secondary": "#A8BED4", "text_tertiary": "#6B8299",
                "meta": "#5C728A",
                "text": "#A8BED4", "muted": "#9FB3C8", "divider": "#2a4a5e",
                "main_text": "#DCE7F3", "main_muted": "#A8BED4", "line": "#1e3347",
                "accent": "#6bb3d9", "tab_active": "#1e3a52", "tab_inactive": "#162a3a",
                "tab_border_active": "#2e5470", "tab_border_inactive": "#1e3347",
                "tab_text_active": "#EAF2FF", "tab_text_inactive": "#6B8299",
                "panel": "#0f1e2d", "panel_border": "#1e3347", "toggle": "#1e3a52",
                "input_bg": "#0d1a27", "input_text": "#DCE7F3", "input_border": "#2e4a5e",
                "research_panel": "#0f1e2d", "card_shadow": "#1a3a52",
                "grad_a": "#0b1826", "grad_b": "#0d1f30", "wordmark": "#EAF2FF",
                "meter_bg": "#1a3347", "meter_fill": "#6bb3d9",
                "progress_bg": "#1a3347", "progress_fill": "#6bb3d9",
                "service_ok": "#56b97a", "service_off": "#e05858",
                "btn_bg": "#1e3a52", "btn_text": "#A8BED4", "btn_border": "#2e5470",
                "dot_pattern": "#0f1e2d", "powered_by": "#5C728A",
                "reason_complete": "#56b97a", "reason_active": "#6bb3d9",
                "reason_pending": "#4f6f84", "reason_connector": "#1f3447",
                "reason_panel": "#0f1e2d",
                "reason_title": "#9FB3C8", "reason_subtitle": "#5C728A",
                "reason_row_text": "#DCE7F3", "reason_row_subtext": "#6B8299",
                "reason_edge": "#2b4a5e", "reason_shadow": "#0a121b",
                "reason_glass_hi": "#234057", "reason_pending_outline": "#61869b",
            }
        return {
            "background": "#e8f2f8", "rail": "#ffffff", "rail_border": "#b7c9d6",
            "text": "#1a3a4f", "muted": "#4a6a7d", "divider": "#9fb8c8",
            "main_text": "#1a3a4f", "main_muted": "#5f7d90", "line": "#b7c9d6",
            "accent": "#4a89b0", "tab_active": "#d5e8f3", "tab_inactive": "#edf3f7",
            "tab_border_active": "#98b4c4", "tab_border_inactive": "#c6d5df",
            "tab_text_active": "#1a3a4f", "tab_text_inactive": "#7a9aad",
            "panel": "#f7fbff", "panel_border": "#d4e1ea", "toggle": "#dcecf5",
            "input_bg": "#ffffff", "input_text": "#1a3a4f", "input_border": "#9fb8c8",
            "research_panel": "#f7fbff", "card_shadow": "#cfdbe6",
            "grad_a": "#e8f2f8", "grad_b": "#daeaf4", "wordmark": "#9abcce",
            "meter_bg": "#c8dde8", "meter_fill": "#4a89b0",
            "progress_bg": "#c8dde8", "progress_fill": "#4a89b0",
            "service_ok": "#3a9a5a", "service_off": "#c04040",
            "btn_bg": "#dceef8", "btn_text": "#1a3a4f", "btn_border": "#98b4c4",
            "dot_pattern": "#d8eaf4", "powered_by": "#b8d0de",
            "reason_complete": "#3a9a5a", "reason_active": "#4a89b0",
            "reason_pending": "#8aa5b5", "reason_connector": "#c6d8e3",
            "reason_panel": "#f3f9fd",
            "reason_title": "#1d455d", "reason_subtitle": "#62869b",
            "reason_row_text": "#1b3f55", "reason_row_subtext": "#6d8fa2",
            "reason_edge": "#bfd5e2", "reason_shadow": "#bfd3df",
            "reason_glass_hi": "#ffffff", "reason_pending_outline": "#91adbd",
        }

    def _lerp_color(self, c1, c2, t):
        def h2r(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        r1, g1, b1 = h2r(c1)
        r2, g2, b2 = h2r(c2)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

    def _orb_color_for_agent(self):
        agent = self.state.agent_focus
        dark = self.state.ui_mode == "dark"
        colors = {
            "SHOPPING": ("#1a4a28", "#6ab88a") if dark else ("#c8ecd6", "#56b97a"),
            "CALENDAR": ("#3a2800", "#c8922a") if dark else ("#f0e0b0", "#e0a238"),
            "RESEARCH": ("#1a0d38", "#9a7ad6") if dark else ("#d8ccf4", "#8b6be8"),
            "GENERAL":  ("#0d1e2e", "#7aaabb") if dark else ("#c8d8e8", "#7aa7c2"),
            "BRAIN":    ("#0d2a42", "#6aafd6") if dark else ("#c8e0f4", "#49a1e6"),
        }
        return colors.get(agent, ("#1a3a52", "#88cbe8") if dark else ("#caeaf8", "#e5f8ff"))

    def _check_service(self, key):
        return bool(os.getenv(key, "").strip())

    def _orb_label(self):
        s = self.state
        if self.is_thinking:
            labels = {
                "SHOPPING": "SHOPPING", "CALENDAR": "SCHEDULING",
                "RESEARCH": "RESEARCHING", "GENERAL": "THINKING", "BRAIN": "ROUTING",
            }
            return labels.get(s.agent_focus, "THINKING")
        if s.listening:
            return "LISTENING"
        if s.is_speaking:
            return "SPEAKING"
        return "IDLE"

    # ── drawing ──

    def redraw(self, event=None) -> None:
        s = self.state
        theme = self._theme()
        self._sync_reasoning_status()
        w = self.bg_canvas.winfo_width()
        h = self.bg_canvas.winfo_height()
        self.bg_canvas.delete("all")
        self.tab_hitboxes.clear()
        self.agent_hitboxes.clear()
        self.theme_toggle_hitbox = None
        self.speed_hitboxes.clear()
        self.agent_toggle_hitboxes.clear()
        self.clear_history_hitbox = None
        self.context_section_hitboxes.clear()
        self.context_add_hitbox = None
        self.context_doc_delete_hitboxes.clear()
        self.context_clear_docs_hitbox = None
        self.reasoning_row_hitboxes = []

        self.root.configure(bg=theme["background"])
        self.stage.configure(bg=theme["background"])

        # gradient background
        t = (math.sin(self.gradient_phase) + 1) / 2
        bg_color = self._lerp_color(theme["grad_a"], theme["grad_b"], t)
        self.bg_canvas.configure(bg=bg_color)
        self.bg_canvas.create_rectangle(0, 0, w, h, fill=bg_color, outline="")

        # subtle dot pattern on main panel
        rail_w = max(260, min(300, int(w * 0.26)))
        rail_x = max(0, w - rail_w)
        main_w = max(400, rail_x)
        self._draw_dot_pattern(0, 0, rail_x, h, theme)

        # border glow
        border_col = "#2a5a7a" if self.state.ui_mode == "dark" else "#88b8cc"
        self.bg_canvas.create_rectangle(0, 0, w-1, h-1, fill="", outline=border_col, width=2)
        self.bg_canvas.create_rectangle(1, 1, w-2, h-2, fill="", outline=border_col, width=1)

        # rail
        self.bg_canvas.create_rectangle(rail_x, 0, w, h, fill=theme["rail"], outline="")
        self.bg_canvas.create_line(rail_x, 0, rail_x, h, fill=theme["rail_border"], width=2)
        self._draw_agent_rail(rail_x, w, h)

        # subtle left brand block
        brand_x = 24
        brand_y = 18
        if self.logo_tk is not None:
            self.bg_canvas.create_image(brand_x, brand_y, image=self.logo_tk, anchor="nw")
        brand_text_x = brand_x + (46 if self.logo_tk is not None else 0)
        self.bg_canvas.create_text(brand_text_x, brand_y + 2, text="OpenSight",
                                   fill=self._lerp_color(theme["wordmark"], theme["muted"], 0.35),
                                   font=(self.font_ui, 18, "bold"), anchor="nw")
        self.bg_canvas.create_text(brand_text_x, brand_y + 30,
                                   text="Technology that Adapts to You",
                                   fill=theme.get("meta", theme["muted"]),
                                   font=self.typo["mono_micro"], anchor="nw")

        # orb
        orb_r = max(32, min(52, main_w // 20))
        cx = max(200, int(main_w * 0.50))
        cy = h - orb_r - 50
        s.orb_cx, s.orb_cy, s.orb_r = cx, cy, orb_r

        orb_ring, orb_core = self._orb_color_for_agent()
        if s.listening:
            phase = self.state.pulse_step % 15
            rr = max(orb_r + 3, orb_r + 14 - phase)
            self.bg_canvas.create_oval(cx-rr, cy-rr, cx+rr, cy+rr, fill=orb_ring, outline="")
        else:
            self.bg_canvas.create_oval(cx-orb_r-8, cy-orb_r-8, cx+orb_r+8, cy+orb_r+8, fill=orb_ring, outline="")

        self.bg_canvas.create_oval(cx-orb_r, cy-orb_r, cx+orb_r, cy+orb_r, fill=orb_core, outline="")
        self._draw_mic_icon(cx, cy, "#245972" if s.listening else "#356985")

        # orb label — dynamic
        orb_label = self._orb_label()
        self.bg_canvas.create_text(cx, cy-orb_r-14, text=orb_label,
                                    fill=theme["muted"], font=self.typo["mono_label"])

        if self.waveform_mode != "off":
            self._draw_waveform(cx, cy + orb_r + 16, theme)

        # powered by strip
        self.bg_canvas.create_text(cx, h - 18, text="Gemini  ·  Deepgram  ·  ElevenLabs",
                                    fill=theme["powered_by"], font=self.typo["mono_micro"], anchor="center")

        # transcript zones
        stack_cx = cx
        ai_text_w = max(400, int(main_w * 0.88))
        user_text_w = max(260, int(main_w * 0.60))
        top_zone_y = int(h * 0.22)
        divider_y = int(h * 0.40)
        bottom_zone_y = int(h * 0.54)
        lx = stack_cx - (ai_text_w // 2)

        # YOU zone
        self.bg_canvas.create_text(lx, top_zone_y-24, text=self._caps("YOU"),
                                    fill=theme["muted"], font=self.typo["label"], anchor="w")
        if self.user_timestamp:
            self.bg_canvas.create_text(lx+36, top_zone_y-24, text=self.user_timestamp,
                                        fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="w")

        user_display = s.live_transcript or s.last_user_text or "Speak and your words will appear here..."
        self.bg_canvas.create_text(stack_cx, top_zone_y, text=user_display,
                                    fill=theme["main_text"] if (s.live_transcript or s.last_user_text) else theme["main_muted"],
                                    font=self.typo["body_large"], width=user_text_w, justify="center", anchor="center")

        if s.listening:
            self._draw_mic_meter(stack_cx, top_zone_y+28, user_text_w, theme)

        self.bg_canvas.create_line(stack_cx-160, divider_y, stack_cx+160, divider_y,
                                    fill=theme["accent"], width=1, dash=(6, 4))

        # OPENSIGHT zone
        self.bg_canvas.create_text(lx, bottom_zone_y-26, text=self._caps("OpenSight"),
                                    fill=theme["muted"], font=self.typo["label"], anchor="w")
        if self.ai_timestamp:
            self.bg_canvas.create_text(lx+82, bottom_zone_y-26, text=self.ai_timestamp,
                                        fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="w")

        if self.ai_animation_target:
            self._draw_progress_bar(stack_cx, bottom_zone_y-10, ai_text_w, theme)

        if self.is_thinking:
            if self.research_status:
                self.bg_canvas.create_text(lx, bottom_zone_y, text=self.research_status,
                                            fill=theme["accent"], font=("SF Mono", 12),
                                            width=ai_text_w, justify="left", anchor="nw")
            else:
                dots = "●" * (self.thinking_step % 4) or "●"
                self.bg_canvas.create_text(stack_cx, bottom_zone_y+14, text=dots,
                                            fill=theme["accent"], font=("SF Mono", 20), anchor="center")
        elif self.ai_render_text:
            self.bg_canvas.create_text(lx, bottom_zone_y, text=self.ai_render_text,
                                        fill=theme["main_text"], font=self.typo["body_large"],
                                        width=ai_text_w, justify="left", anchor="nw")
        else:
            self.bg_canvas.create_text(stack_cx, bottom_zone_y+14,
                                        text="Response will appear here...",
                                        fill=theme["main_muted"], font=self.typo["body_large"],
                                        width=ai_text_w, justify="center", anchor="center")

    def _draw_dot_pattern(self, x0, y0, x1, y1, theme):
        spacing = 28
        dc = theme["dot_pattern"]
        for gx in range(x0 + 14, x1, spacing):
            for gy in range(y0 + 14, y1, spacing):
                self.bg_canvas.create_oval(gx-1, gy-1, gx+1, gy+1, fill=dc, outline="")

    def _draw_mic_meter(self, cx, y, width, theme):
        bw = int(width * 0.5)
        x1, x2 = cx - bw//2, cx + bw//2
        self.bg_canvas.create_rectangle(x1, y, x2, y+4, fill=theme["meter_bg"], outline="")
        fw = int(bw * min(1.0, self.mic_level_smooth))
        if fw > 2:
            self.bg_canvas.create_rectangle(x1, y, x1+fw, y+4, fill=theme["meter_fill"], outline="")

    def _draw_progress_bar(self, cx, y, width, theme):
        if not self.ai_animation_target:
            return
        bw = int(width * 0.4)
        x1 = cx - bw//2
        self.bg_canvas.create_rectangle(x1, y, x1+bw, y+2, fill=theme["progress_bg"], outline="")
        fw = int(bw * self.ai_animation_index / max(1, len(self.ai_animation_target)))
        if fw > 0:
            self.bg_canvas.create_rectangle(x1, y, x1+fw, y+2, fill=theme["progress_fill"], outline="")

    def _draw_waveform(self, cx, y, theme):
        bar_count = 5
        bar_w = 8
        gap = 7
        max_h = 28
        min_h = 7
        total_w = bar_count * bar_w + (bar_count - 1) * gap
        start_x = cx - total_w // 2

        base_light = "#8fd7ff" if self.state.ui_mode == "dark" else "#5ba6d5"
        base_dark = "#2f7fb0" if self.state.ui_mode == "dark" else "#2f7fb0"

        for i, level in enumerate(self.waveform_bars):
            height = int(min_h + level * (max_h - min_h))
            x1 = start_x + i * (bar_w + gap)
            x2 = x1 + bar_w
            y1 = y - height // 2
            y2 = y + height // 2

            center_distance = abs(i - 2) / 2.0
            bar_col = self._lerp_color(base_light, base_dark, center_distance * 0.7)
            shine_col = self._lerp_color("#d8f1ff", bar_col, 0.55)

            self._rounded_rect(x1, y1, x2, y2, radius=bar_w // 2, fill=bar_col, outline="")
            self._rounded_rect(x1 + 1, y1 + 1, x2 - 1, y1 + max(2, height // 3),
                               radius=max(1, (bar_w // 2) - 1), fill=shine_col, outline="")

    def _draw_mic_icon(self, cx, cy, color):
        self.bg_canvas.create_oval(cx-9, cy-14, cx+9, cy+4, fill=color, outline="")
        self.bg_canvas.create_rectangle(cx-4, cy+1, cx+4, cy+14, fill=color, outline="")
        self.bg_canvas.create_arc(cx-12, cy-7, cx+12, cy+9, start=200, extent=140,
                                   style="arc", outline=color, width=2)
        self.bg_canvas.create_line(cx, cy+14, cx, cy+21, fill=color, width=2)
        self.bg_canvas.create_line(cx-7, cy+21, cx+7, cy+21, fill=color, width=2)

    def _on_spacebar_press(self, event):
        if not self.state.listening:
            self.toggle_listening()
        return "break"

    def _on_wake(self):
        self._safe_after(0, self._handle_wake)

    def _handle_wake(self):
        if not self.state.listening:
            self.toggle_listening()
        self.state.voice_queue.put("Yes?")

    # ── agent rail ──

    def _draw_agent_rail(self, rail_x, w, h):
        theme = self._theme()
        cl, cr = rail_x + 14, w - 14
        tab_top, tab_h = 12, 28
        tab_w = (cr - cl - 8) // 3
        tabs = {
            "agents":   (cl, tab_top, cl + tab_w, tab_top+tab_h),
            "settings": (cl + tab_w + 4, tab_top, cl + (tab_w * 2) + 4, tab_top+tab_h),
            "context":  (cl + (tab_w * 2) + 8, tab_top, cr, tab_top+tab_h),
        }
        self.tab_hitboxes = tabs

        for key, label in (("agents", "Agents"), ("settings", "Settings"), ("context", "Context")):
            x1, y1, x2, y2 = tabs[key]
            active = self.state.active_right_tab == key
            self._rounded_rect(x1, y1, x2, y2, radius=10,
                               fill=theme["tab_active"] if active else theme["tab_inactive"],
                               outline=theme["tab_border_active"] if active else theme["tab_border_inactive"])
            self.bg_canvas.create_text((x1+x2)//2, y1+8, text=label,
                                       fill=theme["tab_text_active"] if active else theme["tab_text_inactive"],
                                       font=self.typo["label"], anchor="n")

        if self.state.active_right_tab == "settings":
            self._destroy_context_doc_inputs()
            self._draw_settings_panel(cl, cr, h)
            return

        if self.state.active_right_tab == "context":
            self._destroy_username_entry()
            self._draw_context_panel(cl, cr, h)
            return

        self._destroy_username_entry()
        self._destroy_context_doc_inputs()
        self.bg_canvas.create_text(rail_x+18, 50, text=self._caps("Brain / Agents"),
                                   fill=theme["muted"], font=self.typo["label"], anchor="nw")
        if self.state.username:
            self.bg_canvas.create_text(rail_x+18, 66, text=f"User: {self.state.username}",
                                       fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="nw")

        reason_panel_height = 292
        chain_bottom = h - 28
        chain_top = chain_bottom - reason_panel_height
        y_cursor = 84
        for agent in AGENT_ORDER:
            yt, yb = y_cursor, y_cursor + 48
            if yb > chain_top - 10:
                break
            self.agent_hitboxes[agent] = (cl, yt, cr, yb)
            active = agent == self.state.agent_focus
            disabled = agent in self.disabled_agents
            flash = self.agent_flash.get(agent, 0)
            fill, outline, title_color, detail_color, accent = self._agent_card_colors(agent, active)

            if disabled:
                fill, outline, title_color, detail_color, accent = (
                    theme["panel"], theme["panel_border"],
                    theme["muted"], theme["muted"], theme["muted"])
            elif active:
                # single soft glow halo
                glow = self._agent_glow_color(agent)
                self._rounded_rect(cl-7, yt-7, cr+7, yb+7, radius=17, fill=glow, outline="")
                # slightly lift fill toward accent for active card
                fill = self._lerp_color(fill, accent, 0.12)

            if flash > 0:
                fill = self._lerp_color(fill, accent, flash / 8.0)

            self._rounded_rect(cl, yt, cr, yb, radius=12, fill=fill, outline=outline, width=1)

            # 4 px colored left accent bar
            bar_color = theme["muted"] if disabled else accent
            self.bg_canvas.create_rectangle(cl, yt + 10, cl + 4, yb - 10,
                                            fill=bar_color, outline="")

            # status dot (larger, pulsing when active)
            dy_center = yt + 24
            dx = cl + 20
            dr = 5 if not active else 6 + (self.state.pulse_step % 3)
            dot_color = theme["muted"] if disabled else accent
            self.bg_canvas.create_oval(dx-dr, dy_center-dr, dx+dr, dy_center+dr,
                                       fill=dot_color, outline="")
            if active and not disabled:
                self.bg_canvas.create_oval(dx-2, dy_center-2, dx+2, dy_center+2,
                                           fill="#ffffff", outline="")

            # agent name
            self.bg_canvas.create_text(cl + 34, yt + 9, text=agent,
                                       fill=title_color, font=self.typo["mono_label"], anchor="nw")

            # detail line + active badge
            detail = self._agent_detail(agent)
            if active and not disabled:
                self.bg_canvas.create_text(cl + 34, yt + 27, text=detail.upper(),
                                           fill=accent, font=self.typo["micro"], anchor="nw")
                # "ACTIVE ↗" pill in top-right of card
                bx2 = cr - 7
                bx1 = bx2 - 46
                by1, by2 = yt + 7, yt + 21
                self._rounded_rect(bx1, by1, bx2, by2, radius=5,
                                   fill=self._lerp_color(fill, accent, 0.20), outline=accent, width=1)
                self.bg_canvas.create_text((bx1 + bx2) // 2, by1 + 2,
                                           text="ACTIVE ↗",
                                           fill=accent, font=self.typo["mono_tiny"], anchor="n")
            else:
                self.bg_canvas.create_text(cl + 34, yt + 27, text=detail,
                                           fill=detail_color, font=self.typo["micro"], anchor="nw")

            y_cursor = yb + 8

            if agent == "RESEARCH" and self.state.research_panel_open:
                pt, pb = y_cursor, y_cursor + 76
                if pb > chain_top - 6:
                    self.state.research_panel_open = False
                    break
                self._rounded_rect(cl+4, pt, cr, pb, radius=10,
                                   fill=theme["research_panel"], outline=theme["panel_border"])
                self.bg_canvas.create_text(cl+12, pt+8, text=self._caps("Recent Papers"),
                                           fill=theme["text"], font=self.typo["section"], anchor="nw")
                recent = self.state.research_history[-3:]
                if recent:
                    for idx, title in enumerate(reversed(recent), 1):
                        self.bg_canvas.create_text(cl+12, pt+8+(idx*16), text=f"{idx}. {title}",
                                                   fill=theme.get("text_secondary", theme["muted"]), font=self.typo["micro"],
                                                   anchor="nw", width=(cr-cl-22), justify="left")
                else:
                    self.bg_canvas.create_text(cl+12, pt+28, text="No research history yet.",
                                               fill=theme.get("text_tertiary", theme["muted"]), font=self.typo["mono_tiny"], anchor="nw")
                y_cursor = pb + 8

        self._draw_reasoning_chain(cl, cr, chain_top, chain_bottom)
        self.bg_canvas.create_text((cl+cr)//2, h-16, text="OpenSight v1.0",
                                   fill=theme.get("meta", theme["muted"]), font=self.typo["mono_tiny"], anchor="center")

    def _agent_glow_color(self, agent):
        dark = self.state.ui_mode == "dark"
        d = {"BRAIN": "#0a1e3a", "SHOPPING": "#0a1e12", "CALENDAR": "#1e1400",
             "RESEARCH": "#120a28", "GENERAL": "#0a1420"}
        l = {"BRAIN": "#c8e0f4", "SHOPPING": "#c8ecd6", "CALENDAR": "#f0e0b0",
             "RESEARCH": "#d8ccf4", "GENERAL": "#c8d8e8"}
        return (d if dark else l).get(agent, "#0b1826" if dark else "#e8f2f8")

    # ── settings panel ──

    def _draw_settings_panel(self, left, right, h):
        theme = self._theme()
        cw = right - left
        mid = (left + right) // 2

        self.bg_canvas.create_text(mid, 50, text=self._caps("Settings"),
                                   fill=theme["accent"], font=self.typo["label"], anchor="center")
        y = 70

        # appearance
        self.bg_canvas.create_text(left+8, y, text=self._caps("Appearance"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        tw = cw - 16
        self.theme_toggle_hitbox = (left+8, y, left+8+tw, y+28)
        self._rounded_rect(left+8, y, left+8+tw, y+28, radius=8,
                           fill=theme["toggle"], outline=theme["input_border"])
        self.bg_canvas.create_text(mid, y+7,
                                   text="🌙  Dark Mode" if self.state.ui_mode == "dark" else "☀️  Light Mode",
                                   fill=theme["text"], font=self.typo["label"], anchor="n")
        y += 44

        # user name
        self.bg_canvas.create_text(left+8, y, text=self._caps("User Name"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        self._ensure_username_entry(left+8, y, cw-16)
        y += 40

        # voice speed
        self.bg_canvas.create_text(left+8, y, text=self._caps("Voice Speed"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        bw = (cw - 16) // 3 - 2
        for i, spd in enumerate(["slow", "normal", "fast"]):
            bx1 = left + 8 + i * (bw + 4)
            bx2 = bx1 + bw
            self.speed_hitboxes[spd] = (bx1, y, bx2, y+24)
            active = self.voice_speed == spd
            self._rounded_rect(bx1, y, bx2, y+24, radius=6,
                               fill=theme["accent"] if active else theme["panel"],
                               outline=theme["accent"] if active else theme["panel_border"])
            self.bg_canvas.create_text((bx1+bx2)//2, y+5, text=spd.capitalize(),
                                       fill="#ffffff" if active else theme["muted"],
                                       font=self.typo["label_soft"], anchor="n")
        y += 40

        self.bg_canvas.create_line(left+8, y, right-8, y, fill=theme["panel_border"], width=1)
        y += 14

        # agent toggles with animated knobs
        self.bg_canvas.create_text(left+8, y, text=self._caps("Active Agents"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        for agent in AGENT_ORDER:
            enabled = agent not in self.disabled_agents
            _, _, _, _, accent = self._agent_card_colors(agent, True)
            self.bg_canvas.create_oval(left+8, y+3, left+16, y+11,
                                       fill=accent if enabled else theme["panel_border"], outline="")
            self.bg_canvas.create_text(left+22, y, text=agent,
                                       fill=theme["text"] if enabled else theme["muted"],
                                       font=self.typo["mono_label"], anchor="nw")

            # animated pill toggle
            pw, ph = 36, 18
            px, py = right-pw-8, y
            self.agent_toggle_hitboxes[agent] = (px, py, px+pw, py+ph)

            # smooth knob position
            knob_t = self.toggle_knob_pos.get(agent, 1.0 if enabled else 0.0)
            pill_bg = self._lerp_color(theme["panel_border"], theme["accent"], knob_t)
            self._rounded_rect(px, py, px+pw, py+ph, radius=9, fill=pill_bg, outline="")

            # knob
            knob_r = 7
            knob_x = int(px + knob_r + 2 + knob_t * (pw - 2*(knob_r+2)))
            knob_y = py + ph//2
            self.bg_canvas.create_oval(knob_x-knob_r, knob_y-knob_r,
                                       knob_x+knob_r, knob_y+knob_r,
                                       fill="#ffffff", outline="")
            y += 24

        self.bg_canvas.create_line(left+8, y+2, right-8, y+2, fill=theme["panel_border"], width=1)
        y += 16

        # connected services
        self.bg_canvas.create_text(left+8, y, text=self._caps("Connected Services"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        for name, key in [("Deepgram", "DEEPGRAM_API_KEY"), ("ElevenLabs", "ELEVENLABS_API_KEY"),
                          ("Gemini", "GEMINI_API_KEY"), ("Google Cal", "GOOGLE_CLIENT_ID"),
                          ("SerpAPI", "SERPAPI_KEY")]:
            ok = self._check_service(key)
            dc = theme["service_ok"] if ok else theme["service_off"]
            self.bg_canvas.create_oval(left+8, y+3, left+16, y+11, fill=dc, outline="")
            self.bg_canvas.create_text(left+22, y, text=name,
                                       fill=theme["text"], font=self.typo["micro"], anchor="nw")
            self.bg_canvas.create_text(right-8, y, text="✓" if ok else "✗",
                                       fill=dc, font=self.typo["mono_label"], anchor="ne")
            y += 20

        y += 8
        self.clear_history_hitbox = (left+8, y, right-8, y+26)
        self._rounded_rect(left+8, y, right-8, y+26, radius=8,
                           fill=theme["panel"], outline=theme["panel_border"])
        self.bg_canvas.create_text(mid, y+6, text="Clear History",
                                   fill=theme["muted"], font=self.typo["label"], anchor="n")

        self.bg_canvas.create_text(mid, h-16, text="OpenSight v1.0",
                                   fill=theme["panel_border"], font=self.typo["mono_tiny"], anchor="center")

    def _draw_context_panel(self, left, right, h):
        theme = self._theme()
        mid = (left + right) // 2

        self.bg_canvas.create_text(mid, 48, text=self._caps("Context"),
                                   fill=theme["accent"], font=self.typo["label"], anchor="center")
        self.bg_canvas.create_text(mid, 64, text="Live session context · not saved",
                                   fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="center")

        sections = [
            ("about", "About You"),
            ("recent", "Recent Context"),
            ("documents", f"Documents ({len(self.context_documents)})"),
        ]

        y = 84
        body_padding = 12
        section_spacing = 10

        for key, title in sections:
            is_open = self.context_open_section == key
            header_h = 30
            x1, x2 = left + 8, right - 8
            self.context_section_hitboxes[key] = (x1, y, x2, y + header_h)

            self._rounded_rect(
                x1, y, x2, y + header_h, radius=9,
                fill=theme["tab_active"] if is_open else theme["panel"],
                outline=theme["tab_border_active"] if is_open else theme["panel_border"],
            )
            self.bg_canvas.create_text(x1 + 12, y + 7, text=title,
                                       fill=theme["text"], font=self.typo["label"], anchor="nw")
            self.bg_canvas.create_text(x2 - 10, y + 7, text="▾" if is_open else "▸",
                                       fill=theme["muted"], font=self.typo["label"], anchor="ne")

            y += header_h + 6

            if is_open:
                max_body_h = max(100, (h - 44) - y)
                body_h = min(282, max_body_h)

                self._rounded_rect(x1, y, x2, y + body_h, radius=11,
                                   fill=theme["panel"], outline=theme["panel_border"])

                if key == "documents":
                    self._draw_documents_section_content(x1, y, x2, body_h, theme)
                else:
                    lines = self._context_section_lines(key)
                    line_h = 17
                    max_lines = max(3, (body_h - (body_padding * 2)) // line_h)
                    render_lines = lines[:max_lines]
                    if len(lines) > max_lines:
                        render_lines[-1] = "…"

                    self.bg_canvas.create_text(
                        x1 + 12,
                        y + body_padding,
                        text="\n".join(render_lines),
                        fill=theme["text"],
                        font=self.typo["micro"],
                        anchor="nw",
                        width=max(90, (x2 - x1) - 24),
                        justify="left",
                    )

                y += body_h + section_spacing

            if y > h - 70:
                break

        self.bg_canvas.create_text(mid, h-16, text="Single-open view",
                                   fill=theme.get("meta", theme["muted"]), font=self.typo["mono_tiny"], anchor="center")

    def _draw_documents_section_content(self, x1: int, y: int, x2: int, body_h: int, theme: dict) -> None:
        pad = 10
        inner_w = max(100, (x2 - x1) - (pad * 2))
        cursor_y = y + pad

        self._ensure_context_doc_inputs(theme)

        self.bg_canvas.create_text(x1 + pad, cursor_y, text="ADD DOCUMENT",
                                   fill=theme["muted"], font=self.typo["mono_label"], anchor="nw")
        cursor_y += 16

        self.bg_canvas.create_text(x1 + pad, cursor_y, text="Title",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")
        cursor_y += 12
        self.bg_canvas.create_window(x1 + pad, cursor_y, width=inner_w - 152, height=22,
                                     anchor="nw", window=self.context_doc_title_entry)

        add_x1 = x2 - pad - 66
        add_y1 = cursor_y
        add_x2 = x2 - pad
        add_y2 = cursor_y + 22
        self.context_add_hitbox = (add_x1, add_y1, add_x2, add_y2)
        self._rounded_rect(add_x1, add_y1, add_x2, add_y2, radius=7,
                           fill=theme["btn_bg"], outline=theme["btn_border"])
        self.bg_canvas.create_text((add_x1 + add_x2) // 2, add_y1 + 5, text="Add",
                                   fill=theme["btn_text"], font=self.typo["label_soft"], anchor="n")

        clear_x1 = add_x1 - 72
        clear_x2 = add_x1 - 6
        self.context_clear_docs_hitbox = (clear_x1, add_y1, clear_x2, add_y2)
        self._rounded_rect(clear_x1, add_y1, clear_x2, add_y2, radius=7,
                           fill=theme["panel"], outline=theme["panel_border"])
        self.bg_canvas.create_text((clear_x1 + clear_x2) // 2, add_y1 + 5, text="Clear",
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="n")

        cursor_y += 30
        self.bg_canvas.create_text(x1 + pad, cursor_y, text="Summary / Context",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")
        cursor_y += 12
        self.bg_canvas.create_window(x1 + pad, cursor_y, width=inner_w, height=22,
                                     anchor="nw", window=self.context_doc_note_entry)

        cursor_y += 34
        self.bg_canvas.create_line(x1 + pad, cursor_y, x2 - pad, cursor_y, fill=theme["panel_border"], width=1)
        cursor_y += 8

        self.bg_canvas.create_text(x1 + pad, cursor_y, text="YOUR DOCUMENTS",
                                   fill=theme["muted"], font=self.typo["mono_label"], anchor="nw")
        cursor_y += 16

        if not self.context_documents:
            self.bg_canvas.create_text(x1 + pad, cursor_y,
                                       text="No documents yet. Type above and press Add.",
                                       fill=theme["text"], font=self.typo["micro"], anchor="nw",
                                       width=inner_w, justify="left")
            return

        max_rows = 4
        start_idx = max(0, len(self.context_documents) - max_rows)
        visible_indices = list(range(start_idx, len(self.context_documents)))[::-1]

        for display_pos, doc_idx in enumerate(visible_indices, 1):
            if cursor_y > y + body_h - 44:
                break

            doc = self.context_documents[doc_idx]
            card_x1, card_x2 = x1 + pad, x2 - pad
            card_y1, card_y2 = cursor_y, cursor_y + 40
            self._rounded_rect(card_x1, card_y1, card_x2, card_y2, radius=8,
                               fill=self._lerp_color(theme["panel"], theme["tab_active"], 0.25),
                               outline=theme["panel_border"])

            title = (doc.get("title") or f"Context {display_pos}")[:36]
            summary = (doc.get("summary") or "")[:62]

            self.bg_canvas.create_text(card_x1 + 8, card_y1 + 5, text=f"{display_pos}. {title}",
                                       fill=theme["text"], font=self.typo["label"], anchor="nw")
            if summary:
                self.bg_canvas.create_text(card_x1 + 10, card_y1 + 22, text=summary,
                                           fill=theme.get("text_secondary", theme["muted"]),
                                           font=self.typo["mono_tiny"], anchor="nw",
                                           width=max(80, card_x2 - card_x1 - 84), justify="left")

            del_x1, del_x2 = card_x2 - 58, card_x2 - 8
            del_y1, del_y2 = card_y1 + 8, card_y1 + 28
            self.context_doc_delete_hitboxes[doc_idx] = (del_x1, del_y1, del_x2, del_y2)
            self._rounded_rect(del_x1, del_y1, del_x2, del_y2, radius=6,
                               fill=theme["panel"], outline=theme["panel_border"])
            self.bg_canvas.create_text((del_x1 + del_x2) // 2, del_y1 + 4, text="Delete",
                                       fill=theme["muted"], font=self.typo["mono_tiny"], anchor="n")

            cursor_y += 46

    def _context_section_lines(self, key: str) -> list[str]:
        s = self.state
        if key == "about":
            name = s.username.strip() if s.username else "Not set yet"
            speaking_mode = "Listening" if s.listening else "Idle"
            return [
                f"NAME: {name}",
                f"VOICE MODE: {speaking_mode}",
                f"SPEED: {self.voice_speed.capitalize()}",
                "Tip: set your name in Settings > User Name.",
            ]

        if key == "recent":
            if not s.transcript_history:
                return [
                    "No recent context yet.",
                    "Start speaking and your conversation will appear here.",
                ]
            turns = s.transcript_history[-6:]
            return [f"• {entry[:68]}" for entry in turns]

        return []

    def _ensure_context_doc_inputs(self, theme: dict) -> None:
        if self.context_doc_title_entry is None:
            self.context_doc_title_entry = tk.Entry(self.bg_canvas, font=self.typo["micro"], relief="flat")
            self.context_doc_title_entry.bind("<Return>", self._add_context_document_from_inputs)

        if self.context_doc_note_entry is None:
            self.context_doc_note_entry = tk.Entry(self.bg_canvas, font=self.typo["micro"], relief="flat")
            self.context_doc_note_entry.bind("<Return>", self._add_context_document_from_inputs)

        for entry in (self.context_doc_title_entry, self.context_doc_note_entry):
            entry.configure(
                bg=theme["input_bg"], fg=theme["input_text"],
                insertbackground=theme["input_text"],
                highlightthickness=1, highlightbackground=theme["input_border"],
                highlightcolor=theme["accent"], relief="flat", bd=0,
            )

    def _destroy_context_doc_inputs(self):
        if self.context_doc_title_entry is not None:
            self.context_doc_title_entry.destroy()
            self.context_doc_title_entry = None
        if self.context_doc_note_entry is not None:
            self.context_doc_note_entry.destroy()
            self.context_doc_note_entry = None

    def _add_context_document_from_inputs(self, event=None):
        title = (self.context_doc_title_entry.get().strip() if self.context_doc_title_entry else "")
        summary = (self.context_doc_note_entry.get().strip() if self.context_doc_note_entry else "")

        if not title and not summary:
            return "break" if event is not None else None

        if not title:
            title = f"Context {len(self.context_documents) + 1}"

        self.context_documents.append({
            "title": title[:60],
            "summary": summary[:220],
        })
        if len(self.context_documents) > 24:
            self.context_documents = self.context_documents[-24:]

        if self.context_doc_title_entry is not None:
            self.context_doc_title_entry.delete(0, tk.END)
        if self.context_doc_note_entry is not None:
            self.context_doc_note_entry.delete(0, tk.END)

        self.redraw()
        return "break" if event is not None else None

    def _delete_context_document(self, index: int) -> None:
        if 0 <= index < len(self.context_documents):
            self.context_documents.pop(index)
            self.redraw()

    def _clear_context_documents(self) -> None:
        if self.context_documents:
            self.context_documents = []
            self.redraw()

    def _ensure_username_entry(self, x, y, width):
        theme = self._theme()
        if self.username_entry is None:
            self.username_entry = tk.Entry(self.bg_canvas, font=self.typo["body"], relief="flat")
            self.username_entry.insert(0, self.state.username)
            self.username_entry.bind("<Return>", self._commit_username)
            self.username_entry.bind("<FocusOut>", self._commit_username)
        self.username_entry.configure(
            bg=theme["input_bg"], fg=theme["input_text"],
            insertbackground=theme["input_text"],
            highlightthickness=1, highlightbackground=theme["input_border"],
            highlightcolor=theme["accent"], relief="flat", bd=0,
        )
        self.username_window_id = self.bg_canvas.create_window(
            x, y, width=width, height=22, anchor="nw", window=self.username_entry)

    def _destroy_username_entry(self):
        if self.username_entry is not None:
            self.username_entry.destroy()
            self.username_entry = None
            self.username_window_id = None

    def _agent_detail(self, agent):
        return {"BRAIN": "routing requests", "SHOPPING": "scanning options",
                "CALENDAR": "checking schedules", "RESEARCH": "pulling sources",
                "GENERAL": "composing responses"}.get(agent, "idle")

    def _rounded_rect(self, x1, y1, x2, y2, radius, *, fill, outline, width=1):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
                  x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
                  x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        self.bg_canvas.create_polygon(points, smooth=True, splinesteps=24,
                                       fill=fill, outline=outline, width=width)

    def _agent_card_colors(self, agent, active):
        if self.state.ui_mode == "dark":
            palette = {
                "BRAIN":    ("#173149", "#2f5574", "#8eb9d4", "#7290a3", "#7fb7de"),
                "SHOPPING": ("#173427", "#2d5a43", "#9bcfb4", "#7f9f90", "#89cfa6"),
                "CALENDAR": ("#3a2f18", "#6a5732", "#d8bf89", "#b09a6f", "#d8b471"),
                "RESEARCH": ("#2a2244", "#4f4272", "#b7a8da", "#9688ba", "#a993dd"),
                "GENERAL":  ("#1e3342", "#395a6f", "#9dc3d6", "#809eaf", "#8cb9ce"),
            }
            inactive = {
                "BRAIN":    ("#162c3e", "#2d4b64", "#86adc7", "#6f8a9f", "#7fb7de"),
                "SHOPPING": ("#162f24", "#2a503d", "#92c4aa", "#759788", "#89cfa6"),
                "CALENDAR": ("#352b18", "#5f4f2e", "#ccb57f", "#a7936a", "#d8b471"),
                "RESEARCH": ("#27203f", "#483d68", "#ad9fd1", "#8f83b2", "#a993dd"),
                "GENERAL":  ("#1c2f3d", "#34556a", "#94bbcf", "#7897a9", "#8cb9ce"),
            }
        else:
            palette = {
                "BRAIN":    ("#e6f1fb", "#b7d2e8", "#2d5368", "#68859a", "#83b7da"),
                "SHOPPING": ("#eaf6ef", "#b9dcc6", "#2e5a43", "#6f8f7e", "#90ceab"),
                "CALENDAR": ("#fff4e3", "#e8d0a4", "#6d5629", "#9e8759", "#d7b778"),
                "RESEARCH": ("#f1ecfb", "#ccbce9", "#56437f", "#8373a8", "#a994d8"),
                "GENERAL":  ("#eaf2f7", "#bfd1dd", "#375266", "#708999", "#91b8cb"),
            }
            inactive = {
                "BRAIN":    ("#edf4fb", "#c3d9eb", "#3a5c70", "#7591a4", "#83b7da"),
                "SHOPPING": ("#eef8f2", "#c4e0cf", "#3a624b", "#789385", "#90ceab"),
                "CALENDAR": ("#fff6e8", "#edd8b1", "#755e2f", "#a58e5f", "#d7b778"),
                "RESEARCH": ("#f4f0fc", "#d3c5ec", "#5e4a85", "#8a7bad", "#a994d8"),
                "GENERAL":  ("#edf4f8", "#c7d7e1", "#415a6d", "#7a91a0", "#91b8cb"),
            }
        if active:
            return palette.get(agent, ("#eaf2f8", "#bfd5e2", "#3f5b6b", "#6f8896", "#83b7da"))
        return inactive.get(agent, ("#edf2f5", "#cbd6df", "#586f7e", "#8798a6", "#91b8cb"))

    # ── reasoning chain ──

    def _reset_reasoning_chain(self):
        now = time.monotonic()
        base = [
            ("Classify intent", "Waiting for request"),
            ("Extract constraints", "Waiting for request"),
            ("Route to agent", "Waiting for request"),
            ("Execute task", "Waiting for request"),
            ("Generate response", "Waiting for request"),
        ]
        self.state.reasoning_steps = [
            {"id": i + 1, "label": label, "status": "pending", "summary": summary}
            for i, (label, summary) in enumerate(base)
        ]
        self.state.reasoning_transition_at = [now] * len(self.state.reasoning_steps)
        self.state.reasoning_active_index = -1
        self.state.reasoning_last_event = "idle"

    def _set_reasoning_step(self, index, status, summary=None, label=None):
        if index < 0 or index >= len(self.state.reasoning_steps):
            return
        step = self.state.reasoning_steps[index]
        if label:
            step["label"] = label[:30]
        if summary:
            step["summary"] = summary[:44]
        if step["status"] != status:
            step["status"] = status
            self.state.reasoning_transition_at[index] = time.monotonic()
        if status == "active":
            self.state.reasoning_active_index = index

    def _activate_reasoning_step(self, index, summary=None, label=None):
        for i in range(index):
            self._set_reasoning_step(i, "complete")
        for i in range(index + 1, len(self.state.reasoning_steps)):
            if self.state.reasoning_steps[i]["status"] != "complete":
                self._set_reasoning_step(i, "pending")
        self._set_reasoning_step(index, "active", summary=summary, label=label)

    def _complete_reasoning_step(self, index, summary=None):
        self._set_reasoning_step(index, "complete", summary=summary)
        if self.state.reasoning_active_index == index:
            self.state.reasoning_active_index = -1

    def _safe_agent_name(self, agent):
        allowed = {"BRAIN", "SHOPPING", "CALENDAR", "RESEARCH", "GENERAL"}
        return agent if agent in allowed else "GENERAL"

    def _sync_reasoning_status(self):
        current = (self.state.agent_focus, self.state.agent_phase)
        if current == self._last_agent_status:
            return
        self._last_agent_status = current

        focus, phase = current
        focus = self._safe_agent_name(focus)
        phase = (phase or "").lower()

        if not self._reasoning_initialized_for_turn:
            return

        if focus == "BRAIN":
            s0 = self.state.reasoning_steps[0]["status"]
            s1 = self.state.reasoning_steps[1]["status"]
            s2 = self.state.reasoning_steps[2]["status"]
            if s0 in ("pending", "active"):
                self._activate_reasoning_step(0, summary="Classifying user intent")
                self._complete_reasoning_step(0, summary="Intent identified")
            if s1 in ("pending", "active"):
                self._activate_reasoning_step(1, summary="Extracting user constraints")
                if phase in {"thinking", "routing"}:
                    self._complete_reasoning_step(1, summary="Constraints extracted")
            if s2 != "complete":
                self._activate_reasoning_step(2, summary="Selecting best specialist agent")
        elif focus in AGENT_ORDER and focus != "BRAIN":
            self._complete_reasoning_step(2, summary=f"Routed to {focus} agent")
            self._activate_reasoning_step(3, summary=f"Executing task with {focus} agent")

    def _draw_reasoning_chain(self, left, right, top, bottom):
        theme = self._theme()
        pulse = (math.sin(time.monotonic() * 6.0) + 1.0) / 2.0

        # panel shadow + glass body
        self._rounded_rect(left + 1, top + 3, right + 1, bottom + 3, radius=14,
                           fill=theme["reason_shadow"], outline="")
        self._rounded_rect(left, top, right, bottom, radius=14,
                           fill=theme["reason_panel"], outline=theme["reason_edge"])
        self._rounded_rect(left + 1, top + 1, right - 1, top + 30, radius=12,
                           fill=self._lerp_color(theme["reason_panel"], theme["reason_glass_hi"], 0.22), outline="")

        # header: title + live step counter
        completed_count = sum(1 for st in self.state.reasoning_steps if st["status"] == "complete")
        total_steps = len(self.state.reasoning_steps)
        self.bg_canvas.create_text(left + 12, top + 10, text=self._caps("Reasoning Flow"),
                                   fill=theme["reason_title"], font=self.typo["label"], anchor="nw")
        counter_color = theme["reason_active"] if completed_count > 0 else theme["reason_subtitle"]
        self.bg_canvas.create_text(right - 10, top + 10,
                                   text=f"{completed_count} / {total_steps}",
                                   fill=counter_color, font=self.typo["mono_tiny"], anchor="ne")
        self.bg_canvas.create_line(left + 10, top + 32, right - 10, top + 32,
                                   fill=theme["reason_connector"], width=1)

        node_x = left + 22
        title_x = left + 40
        start_y = top + 54
        step_gap = 44

        # vertical rail: dim base + bright progress fill
        progress_y = start_y + max(0, completed_count - 1) * step_gap
        if self.state.reasoning_active_index >= 0 and self.state.reasoning_active_index < total_steps:
            i = self.state.reasoning_active_index
            elapsed = time.monotonic() - self.state.reasoning_transition_at[i]
            progress_y = start_y + i * step_gap + min(step_gap * 0.55, elapsed * 70)
        rail_top = start_y
        rail_bottom = start_y + step_gap * (total_steps - 1)
        self.bg_canvas.create_line(node_x, rail_top, node_x, rail_bottom,
                                   fill=theme["reason_connector"], width=2)
        self.bg_canvas.create_line(node_x, rail_top, node_x, min(rail_bottom, int(progress_y)),
                                   fill=theme["reason_active"], width=4)

        for i, step in enumerate(self.state.reasoning_steps):
            y = start_y + i * step_gap
            row_top = y - 14
            row_bottom = y + 22
            self.reasoning_row_hitboxes.append((left + 10, row_top, right - 10, row_bottom))
            hovered = self.reasoning_hover_index == i
            status = step["status"]
            age = time.monotonic() - self.state.reasoning_transition_at[i]

            # row background: always-on highlight for active, hover-only for others
            if status == "active":
                self._rounded_rect(left + 10, row_top, right - 10, row_bottom, radius=8,
                                   fill=self._lerp_color(theme["reason_panel"], theme["reason_active"], 0.09),
                                   outline=self._lerp_color(theme["reason_panel"], theme["reason_active"], 0.35),
                                   width=1)
            elif hovered:
                self._rounded_rect(left + 10, row_top, right - 10, row_bottom, radius=8,
                                   fill=self._lerp_color(theme["reason_panel"], theme["reason_glass_hi"], 0.14),
                                   outline="")

            # node rendering
            if status == "complete":
                self.bg_canvas.create_oval(node_x - 8, y - 8, node_x + 8, y + 8,
                                           fill=theme["reason_complete"], outline=theme["reason_complete"])
                pop = 1.0 + max(0.0, 0.4 - age) * 1.8
                check_size = 9 if pop < 1.15 else 10
                self.bg_canvas.create_text(node_x, y, text="✓", fill="#ffffff",
                                           font=(self.font_mono, check_size, "bold"), anchor="center")
            elif status == "active":
                # outer pulsing ring
                glow_r = 11 + int(4 * pulse)
                self.bg_canvas.create_oval(node_x - glow_r, y - glow_r, node_x + glow_r, y + glow_r,
                                           fill="", outline=theme["reason_active"], width=2)
                # filled node
                self.bg_canvas.create_oval(node_x - 8, y - 8, node_x + 8, y + 8,
                                           fill=theme["reason_active"], outline=theme["reason_active"])
                # inner white core
                self.bg_canvas.create_oval(node_x - 3, y - 3, node_x + 3, y + 3,
                                           fill="#ffffff", outline="")
            else:
                # pending: outline circle with step number inside
                self.bg_canvas.create_oval(node_x - 8, y - 8, node_x + 8, y + 8,
                                           fill=theme["reason_panel"],
                                           outline=theme["reason_pending_outline"], width=2)
                self.bg_canvas.create_text(node_x, y, text=str(i + 1),
                                           fill=theme["reason_pending_outline"],
                                           font=(self.font_mono, 8, "bold"), anchor="center")

            # text colors per status
            if status == "active":
                title_color = theme["reason_active"]
                subtext_color = self._lerp_color(theme["reason_row_subtext"], theme["reason_active"], 0.35)
            elif status == "complete":
                title_color = (self._lerp_color(theme["reason_row_text"], theme["reason_active"], 0.35)
                               if hovered else theme["reason_row_text"])
                subtext_color = theme["reason_row_subtext"]
            else:
                title_color = (self._lerp_color(theme["reason_row_subtext"], theme["reason_active"], 0.35)
                               if hovered else theme["reason_row_subtext"])
                subtext_color = theme["reason_row_subtext"]

            label = step["label"][:28]
            summary = step.get("summary", "")[:42]
            self.bg_canvas.create_text(title_x, y - 10, text=label,
                                       fill=title_color, font=self.typo["section"], anchor="nw")
            self.bg_canvas.create_text(title_x, y + 10, text=summary,
                                       fill=subtext_color, font=(self.font_ui, 10, "normal"), anchor="nw",
                                       width=max(90, right - title_x - 10), justify="left")

    def on_canvas_motion(self, event):
        if self.state.active_right_tab != "agents" or not self.reasoning_row_hitboxes:
            if self.reasoning_hover_index != -1:
                self.reasoning_hover_index = -1
                self.redraw()
            return

        new_hover = -1
        for idx, box in enumerate(self.reasoning_row_hitboxes):
            if self._point_in_box(event.x, event.y, box):
                new_hover = idx
                break
        if new_hover != self.reasoning_hover_index:
            self.reasoning_hover_index = new_hover
            self.redraw()

    # ── click handling ──

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
                        self.redraw()
                    return
            return

        for agent, bbox in self.agent_hitboxes.items():
            if self._point_in_box(event.x, event.y, bbox):
                self.state.agent_focus = agent
                self.state.research_panel_open = (
                    not self.state.research_panel_open if agent == "RESEARCH" else False)
                self.redraw()
                return

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
        self.toggle_knob_pos[agent] = current + diff * 0.25
        self.redraw()
        self.toggle_anim_job = self.root.after(16, lambda: self._animate_toggle(agent, target))

    def _clear_history(self):
        self.state.transcript_history = []
        self.state.research_history = []
        self.context_documents = []
        if self.context_doc_title_entry is not None:
            self.context_doc_title_entry.delete(0, tk.END)
        if self.context_doc_note_entry is not None:
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
        self.user_timestamp = datetime.datetime.now().strftime("%-I:%M %p")
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
        self.ai_timestamp = datetime.datetime.now().strftime("%-I:%M %p")
        self._complete_reasoning_step(3, summary="Execution finished")
        self._activate_reasoning_step(4, summary="Drafting final response")
        self._stop_thinking()
        self._start_ai_response_animation(response)
        self._safe_after(0, self._start_speaking_visual)
        self.redraw()

    def _extract_research_title(self, response, fallback):
        text = re.sub(r"\s+", " ", response).strip()
        for raw in re.split(r"[\n.!?]", text):
            line = re.sub(r"^[\-\u2022\d\.)\s]+", "", raw).strip()
            if len(line) >= 8:
                return line[:90]
        return fallback.strip()[:90]

    def _format_ai_response(self, text):
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return ""
        out = re.sub(r"\s+(Option\s*\d+\s*:)", r"\n• \1", cleaned)
        out = re.sub(r"^(Option\s*\d+\s*:)", r"• \1", out)
        if "Option" not in out:
            out = re.sub(r"([.!?])\s+", r"\1\n", out)
        lines = []
        for line in out.splitlines():
            s = line.strip()
            if not s:
                continue
            indent = "  " if s.startswith("•") else ""
            wrapped = textwrap.wrap(s, width=60, subsequent_indent=indent)
            lines.extend(wrapped if wrapped else [s])
        return "\n".join(lines)

    # ── animations ──

    def trigger_agent_flash(self, agent):
        self.agent_flash[agent] = 8
        self._tick_agent_flash()

    def _tick_agent_flash(self):
        changed = False
        for agent in list(self.agent_flash.keys()):
            if self.agent_flash[agent] > 0:
                self.agent_flash[agent] -= 1
                changed = True
            else:
                del self.agent_flash[agent]
        if changed:
            self.redraw()
            self.root.after(60, self._tick_agent_flash)

    def _start_mic_level_loop(self):
        self._tick_mic_level()

    def _tick_mic_level(self):
        if self.state.listening and not self.state.is_speaking:
            target = random.uniform(0.1, 0.9) if self.state.live_transcript else random.uniform(0.02, 0.3)
            self.mic_level_smooth += (target - self.mic_level_smooth) * 0.25
        else:
            self.mic_level_smooth *= 0.8
        self.mic_level_job = self.root.after(80, self._tick_mic_level)

    def _start_speaking_visual(self):
        self.is_speaking_visual = True
        self.waveform_mode = "active"
        self.waveform_amp_target = 0.92
        self.waveform_speed_target = 0.32
        self._tick_waveform()

    def _stop_speaking_visual(self):
        self.is_speaking_visual = False
        if self.is_thinking:
            self.waveform_mode = "active"
            self.waveform_amp_target = 0.86
            self.waveform_speed_target = 0.30
        elif self.state.listening:
            self.waveform_mode = "idle"
            self.waveform_amp_target = 0.24
            self.waveform_speed_target = 0.22
        else:
            self.waveform_mode = "off"
            self.waveform_amp_target = 0.12
            self.waveform_speed_target = 0.18
            if self.waveform_job:
                self.root.after_cancel(self.waveform_job)
                self.waveform_job = None
        self.waveform_bars = [0.24, 0.36, 0.5, 0.36, 0.24]

    def _tick_waveform(self):
        if self.is_speaking_visual and self.state.is_speaking:
            self.waveform_mode = "active"
            self.waveform_amp_target = 0.92
            self.waveform_speed_target = 0.32
        elif self.is_thinking:
            self.waveform_mode = "active"
            self.waveform_amp_target = 0.86
            self.waveform_speed_target = 0.30
        elif self.state.listening:
            self.waveform_mode = "idle"
            self.waveform_amp_target = 0.24
            self.waveform_speed_target = 0.22
        else:
            self.waveform_mode = "off"

        if self.waveform_mode == "off":
            self.waveform_bars = [0.2, 0.3, 0.42, 0.3, 0.2]
            self.redraw()
            self.waveform_job = None
            return

        self.waveform_amp += (self.waveform_amp_target - self.waveform_amp) * 0.16
        self.waveform_speed += (self.waveform_speed_target - self.waveform_speed) * 0.14
        self.waveform_phase = (self.waveform_phase + self.waveform_speed) % (math.pi * 2)

        profile = [0.52, 0.74, 1.0, 0.74, 0.52]
        delays = [0.44, 0.24, 0.0, 0.24, 0.44]
        for i in range(5):
            wave = (math.sin(self.waveform_phase - delays[i]) + 1.0) / 2.0
            secondary = (math.sin((self.waveform_phase * 1.8) - delays[i] * 1.6) + 1.0) / 2.0
            self.waveform_noise[i] += random.uniform(-0.01, 0.01)
            self.waveform_noise[i] = max(-0.06, min(0.06, self.waveform_noise[i]))
            organic = 0.68 * wave + 0.32 * secondary
            level = 0.18 + self.waveform_amp * profile[i] * organic + self.waveform_noise[i]
            self.waveform_bars[i] = max(0.12, min(1.0, level))

        self.redraw()
        self.waveform_job = self.root.after(50, self._tick_waveform)

    def _start_gradient_loop(self):
        self._tick_gradient()

    def _tick_gradient(self):
        self.gradient_phase = (self.gradient_phase + 0.008) % (math.pi * 2)
        self.redraw()
        self.gradient_job = self.root.after(50, self._tick_gradient)

    def _start_thinking(self):
        self.is_thinking = True
        self.ai_render_text = ""
        self.waveform_mode = "active"
        self.waveform_amp_target = 0.86
        self.waveform_speed_target = 0.30
        self._tick_waveform()
        if self.thinking_job:
            self.root.after_cancel(self.thinking_job)
        self._tick_thinking()

    def _stop_thinking(self):
        self.is_thinking = False
        self.research_status = ""
        if self.state.listening and not self.is_speaking_visual:
            self.waveform_mode = "idle"
            self.waveform_amp_target = 0.24
            self.waveform_speed_target = 0.22
        if self.thinking_job:
            self.root.after_cancel(self.thinking_job)
            self.thinking_job = None

    def _tick_thinking(self):
        if not self.is_thinking:
            return
        self.thinking_step = (self.thinking_step + 1) % 4
        self.redraw()
        self.thinking_job = self.root.after(400, self._tick_thinking)

    def _start_ai_response_animation(self, response):
        self.ai_animation_target = self._format_ai_response(response)
        self.ai_render_text = ""
        self.ai_animation_index = 0
        if self.ai_animation_job:
            self.root.after_cancel(self.ai_animation_job)
            self.ai_animation_job = None
        self._tick_ai_response_animation()

    def _tick_ai_response_animation(self):
        if self.ai_animation_index >= len(self.ai_animation_target):
            self._complete_reasoning_step(4, summary="Response ready")
            self.ai_animation_job = None
            return
        self.ai_animation_index = min(self.ai_animation_index + 4, len(self.ai_animation_target))
        self.ai_render_text = self.ai_animation_target[:self.ai_animation_index]
        self._sync_reasoning_status()
        self.redraw()
        self.ai_animation_job = self.root.after(16, self._tick_ai_response_animation)

    def _start_pulse_loop(self):
        if self.pulse_job:
            self.root.after_cancel(self.pulse_job)
        self._pulse_tick()

    def _stop_pulse_loop(self):
        if self.pulse_job:
            self.root.after_cancel(self.pulse_job)
            self.pulse_job = None

    def _pulse_tick(self):
        if not self.state.listening:
            return
        self.state.pulse_step = (self.state.pulse_step + 1) % 30
        self.redraw()
        self.pulse_job = self.root.after(80, self._pulse_tick)

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
        for job in [self.ai_animation_job, self.gradient_job, self.mic_level_job, self.toggle_anim_job]:
            if job:
                self.root.after_cancel(job)
        s = self.state
        s.session_token += 1
        s.stop_event.set()
        s.shutdown_event.set()
        s.voice_queue.put(None)
        self._stop_pulse_loop()
        self.root.destroy()

    def _on_research_status(self, status: str) -> None:
        self._safe_after(0, self._apply_research_status, status)

    def _apply_research_status(self, status: str) -> None:
        self.research_status = status
        self.redraw()

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