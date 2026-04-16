import math
import time
import tkinter as tk


class DrawMixin:
    def _rounded_rect(self, x1, y1, x2, y2, radius, *, fill, outline, width=1):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
                  x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
                  x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        self.bg_canvas.create_polygon(points, smooth=True, splinesteps=24,
                                      fill=fill, outline=outline, width=width)

    def _agent_detail(self, agent):
        return {"BRAIN": "routing requests", "SHOPPING": "scanning options",
                "CALENDAR": "checking schedules", "RESEARCH": "pulling sources",
                "GENERAL": "composing responses"}.get(agent, "idle")

    def redraw(self, event=None):
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
        if hasattr(self, "context_doc_card_hitboxes"):
            self.context_doc_card_hitboxes.clear()
        if hasattr(self, "pill_remove_hitboxes"):
            self.pill_remove_hitboxes.clear()

        self.root.configure(bg=theme["background"])
        self.stage.configure(bg=theme["background"])

        t = (math.sin(self.gradient_phase) + 1) / 2
        bg_color = self._lerp_color(theme["grad_a"], theme["grad_b"], t)
        self.bg_canvas.configure(bg=bg_color)
        self.bg_canvas.create_rectangle(0, 0, w, h, fill=bg_color, outline="")

        rail_w = max(260, min(300, int(w * 0.26)))
        rail_x = max(0, w - rail_w)
        main_w = max(400, rail_x)
        self._draw_dot_pattern(0, 0, rail_x, h, theme)

        border_col = "#2a5a7a" if self.state.ui_mode == "dark" else "#88b8cc"
        self.bg_canvas.create_rectangle(0, 0, w-1, h-1, fill="", outline=border_col, width=2)
        self.bg_canvas.create_rectangle(1, 1, w-2, h-2, fill="", outline=border_col, width=1)

        self.bg_canvas.create_rectangle(rail_x, 0, w, h, fill=theme["rail"], outline="")
        self.bg_canvas.create_line(rail_x, 0, rail_x, h, fill=theme["rail_border"], width=2)
        self._draw_agent_rail(rail_x, w, h)

        brand_x, brand_y = 24, 18
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
            self.bg_canvas.create_oval(cx-orb_r-8, cy-orb_r-8, cx+orb_r+8, cy+orb_r+8,
                                       fill=orb_ring, outline="")
        self.bg_canvas.create_oval(cx-orb_r, cy-orb_r, cx+orb_r, cy+orb_r, fill=orb_core, outline="")
        self._draw_mic_icon(cx, cy, "#245972" if s.listening else "#356985")
        self.bg_canvas.create_text(cx, cy-orb_r-14, text=self._orb_label(),
                                   fill=theme["muted"], font=self.typo["mono_label"])
        if self.waveform_mode != "off":
            self._draw_waveform(cx, cy + orb_r + 16, theme)
        self.bg_canvas.create_text(cx, h - 18, text="Gemini  ·  Deepgram  ·  ElevenLabs",
                                   fill=theme["powered_by"], font=self.typo["mono_micro"], anchor="center")

        # transcript zones — compressed toward center
        stack_cx = cx
        ai_text_w = max(400, int(main_w * 0.88))
        user_text_w = max(260, int(main_w * 0.60))
        lx = stack_cx - (ai_text_w // 2)
        available_h = cy - orb_r - 80
        center_y = 80 + (available_h // 2)
        top_zone_y    = center_y - 90
        divider_y     = center_y
        bottom_zone_y = center_y + 55

        self.bg_canvas.create_text(lx, top_zone_y - 22, text=self._caps("YOU"),
                                   fill=theme["muted"], font=self.typo["label"], anchor="w")
        if self.user_timestamp:
            self.bg_canvas.create_text(lx + 38, top_zone_y - 22, text=self.user_timestamp,
                                       fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="w")
        user_display = s.live_transcript or s.last_user_text or "Speak and your words will appear here..."
        self.bg_canvas.create_text(stack_cx, top_zone_y, text=user_display,
                                   fill=theme["main_text"] if (s.live_transcript or s.last_user_text) else theme["main_muted"],
                                   font=self.typo["body_large"], width=user_text_w, justify="center", anchor="center")
        if s.listening:
            self._draw_mic_meter(stack_cx, top_zone_y + 28, user_text_w, theme)

        self.bg_canvas.create_line(stack_cx-160, divider_y, stack_cx+160, divider_y,
                                   fill=theme["accent"], width=1, dash=(6, 4))

        # response card
        card_pad = 14
        self._rounded_rect(lx - card_pad, bottom_zone_y - 30,
                           lx + ai_text_w + card_pad, bottom_zone_y + 115, radius=14,
                           fill=self._lerp_color(theme["panel"], bg_color, 0.55),
                           outline=self._lerp_color(theme["panel_border"], bg_color, 0.4))

        self.bg_canvas.create_text(lx, bottom_zone_y - 22, text=self._caps("OpenSight"),
                                   fill=theme["muted"], font=self.typo["label"], anchor="w")
        if self.ai_timestamp:
            self.bg_canvas.create_text(lx + 84, bottom_zone_y - 22, text=self.ai_timestamp,
                                       fill=theme.get("meta", theme["muted"]), font=self.typo["mono_micro"], anchor="w")
        if self.ai_animation_target:
            self._draw_progress_bar(stack_cx, bottom_zone_y - 8, ai_text_w, theme)

        if self.is_thinking:
            if self.research_status:
                self.bg_canvas.create_text(lx, bottom_zone_y, text=self.research_status,
                                           fill=theme["accent"], font=("SF Mono", 12),
                                           width=ai_text_w, justify="left", anchor="nw")
            else:
                dots = "●" * (self.thinking_step % 4) or "●"
                self.bg_canvas.create_text(stack_cx, bottom_zone_y + 14, text=dots,
                                           fill=theme["accent"], font=("SF Mono", 20), anchor="center")
        elif self.ai_render_text:
            display_text = self.ai_render_text
            if self.ai_animation_job and self._cursor_visible:
                display_text += "│"
            self.bg_canvas.create_text(lx, bottom_zone_y, text=display_text,
                                       fill=theme["main_text"], font=self.typo["body_large"],
                                       width=ai_text_w, justify="left", anchor="nw")
        else:
            self.bg_canvas.create_text(stack_cx, bottom_zone_y + 14,
                                       text="Response will appear here...",
                                       fill=theme["main_muted"], font=self.typo["body_large"],
                                       width=ai_text_w, justify="center", anchor="center")

    def _draw_dot_pattern(self, x0, y0, x1, y1, theme):
        dc = theme["dot_pattern"]
        for gx in range(x0 + 14, x1, 28):
            for gy in range(y0 + 14, y1, 28):
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
        bar_w, gap, max_h, min_h = 8, 7, 28, 7
        start_x = cx - (5 * bar_w + 4 * gap) // 2
        base_light = "#8fd7ff" if self.state.ui_mode == "dark" else "#5ba6d5"
        base_dark = "#2f7fb0"
        for i, level in enumerate(self.waveform_bars):
            height = int(min_h + level * (max_h - min_h))
            x1 = start_x + i * (bar_w + gap)
            x2, y1, y2 = x1 + bar_w, y - height // 2, y + height // 2
            bar_col = self._lerp_color(base_light, base_dark, abs(i - 2) / 2.0 * 0.7)
            shine_col = self._lerp_color("#d8f1ff", bar_col, 0.55)
            self._rounded_rect(x1, y1, x2, y2, radius=bar_w//2, fill=bar_col, outline="")
            self._rounded_rect(x1+1, y1+1, x2-1, y1+max(2, height//3),
                               radius=max(1, bar_w//2-1), fill=shine_col, outline="")

    def _draw_mic_icon(self, cx, cy, color):
        self.bg_canvas.create_oval(cx-9, cy-14, cx+9, cy+4, fill=color, outline="")
        self.bg_canvas.create_rectangle(cx-4, cy+1, cx+4, cy+14, fill=color, outline="")
        self.bg_canvas.create_arc(cx-12, cy-7, cx+12, cy+9, start=200, extent=140,
                                  style="arc", outline=color, width=2)
        self.bg_canvas.create_line(cx, cy+14, cx, cy+21, fill=color, width=2)
        self.bg_canvas.create_line(cx-7, cy+21, cx+7, cy+21, fill=color, width=2)

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
            highlightcolor=theme["accent"], relief="flat", bd=0)
        self.bg_canvas.create_window(x, y, width=width, height=24, anchor="nw",
                                     window=self.username_entry)

    def _destroy_username_entry(self):
        if self.username_entry is not None:
            self.username_entry.destroy()
            self.username_entry = None
            self.username_window_id = None

    def _draw_agent_rail(self, rail_x, w, h):
        from agent import AGENT_ORDER
        theme = self._theme()
        cl, cr = rail_x + 14, w - 14
        mid = (cl + cr) // 2
        tab_top, tab_h = 12, 28
        tab_w = (cr - cl - 8) // 3
        tabs = {
            "agents":   (cl, tab_top, cl + tab_w, tab_top + tab_h),
            "settings": (cl + tab_w + 4, tab_top, cl + tab_w*2 + 4, tab_top + tab_h),
            "context":  (cl + tab_w*2 + 8, tab_top, cr, tab_top + tab_h),
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
            if key == "context":
                has_prefs = False
                try:
                    from memory import SessionMemory
                    m = SessionMemory.load()
                    has_prefs = bool(m.preferences.get("allergies") or m.preferences.get("budget")
                                     or m.preferences.get("diet") or m.entities.get("topics"))
                except Exception:
                    pass
                if has_prefs:
                    dot_x, dot_y = x2 - 7, y1 + 7
                    pulse_r = 3 + int(1.5 * ((math.sin(time.monotonic() * 4) + 1) / 2))
                    self.bg_canvas.create_oval(dot_x-pulse_r, dot_y-pulse_r,
                                               dot_x+pulse_r, dot_y+pulse_r,
                                               fill=theme["service_ok"], outline="")

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

        # consistent centered header across all tabs
        self.bg_canvas.create_text(mid, 50, text=self._caps("Brain / Agents"),
                                   fill=theme["accent"], font=self.typo["label"], anchor="center")
        if self.state.username:
            self.bg_canvas.create_text(mid, 65, text=f"User: {self.state.username}",
                                       fill=theme.get("meta", theme["muted"]),
                                       font=self.typo["mono_micro"], anchor="center")

        # auto-fit all agents so GENERAL never clips
        reason_panel_height = 290
        chain_bottom = h - 28
        chain_top = chain_bottom - reason_panel_height
        n = len(AGENT_ORDER)
        available = chain_top - 8 - 84
        card_h = max(38, min(46, (available - 6 * (n - 1)) // n))
        card_gap = max(4, min(8, (available - card_h * n) // max(1, n - 1)))

        y_cursor = 84
        for agent in AGENT_ORDER:
            yt, yb = y_cursor, y_cursor + card_h
            if yb > chain_top - 4:
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
                glow = self._agent_glow_color(agent)
                self._rounded_rect(cl-7, yt-7, cr+7, yb+7, radius=17, fill=glow, outline="")
                fill = self._lerp_color(fill, accent, 0.12)
            if flash > 0:
                fill = self._lerp_color(fill, accent, flash / 8.0)

            self._rounded_rect(cl, yt, cr, yb, radius=10, fill=fill, outline=outline, width=1)
            bar_color = theme["muted"] if disabled else accent
            self.bg_canvas.create_rectangle(cl, yt+7, cl+4, yb-7, fill=bar_color, outline="")

            dy_center, dx = yt + card_h//2, cl + 20
            dr = 5 if not active else 6 + (self.state.pulse_step % 3)
            self.bg_canvas.create_oval(dx-dr, dy_center-dr, dx+dr, dy_center+dr,
                                       fill=theme["muted"] if disabled else accent, outline="")
            if active and not disabled:
                self.bg_canvas.create_oval(dx-2, dy_center-2, dx+2, dy_center+2,
                                           fill="#ffffff", outline="")

            self.bg_canvas.create_text(cl+34, yt+6, text=agent,
                                       fill=title_color, font=self.typo["mono_label"], anchor="nw")
            detail = self._agent_detail(agent)
            if active and not disabled:
                self.bg_canvas.create_text(cl+34, yt+21, text=detail.upper(),
                                           fill=accent, font=self.typo["micro"], anchor="nw")
                bx2, bx1 = cr-7, cr-53
                by1, by2 = yt+6, yt+19
                self._rounded_rect(bx1, by1, bx2, by2, radius=5,
                                   fill=self._lerp_color(fill, accent, 0.20), outline=accent, width=1)
                self.bg_canvas.create_text((bx1+bx2)//2, by1+2, text="ACTIVE ↗",
                                           fill=accent, font=self.typo["mono_tiny"], anchor="n")
            else:
                self.bg_canvas.create_text(cl+34, yt+21, text=detail,
                                           fill=detail_color, font=self.typo["micro"], anchor="nw")
            y_cursor = yb + card_gap

        self._draw_reasoning_chain(cl, cr, chain_top, chain_bottom)
        self.bg_canvas.create_text(mid, h-16, text="OpenSight v1.0",
                                   fill=theme.get("meta", theme["muted"]),
                                   font=self.typo["mono_tiny"], anchor="center")

    def _draw_settings_panel(self, left, right, h):
        from agent import AGENT_ORDER
        theme = self._theme()
        cw = right - left
        mid = (left + right) // 2
        self.bg_canvas.create_text(mid, 50, text=self._caps("Settings"),
                                   fill=theme["accent"], font=self.typo["label"], anchor="center")
        y = 70
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
        self.bg_canvas.create_text(left+8, y, text=self._caps("User Name"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        self._ensure_username_entry(left+8, y, cw-16)
        y += 40
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
            pw, ph = 36, 18
            px, py = right-pw-8, y
            self.agent_toggle_hitboxes[agent] = (px, py, px+pw, py+ph)
            knob_t = self.toggle_knob_pos.get(agent, 1.0 if enabled else 0.0)
            pill_bg = self._lerp_color(theme["panel_border"], theme["accent"], knob_t)
            self._rounded_rect(px, py, px+pw, py+ph, radius=9, fill=pill_bg, outline="")
            knob_r = 7
            knob_x = int(px + knob_r + 2 + knob_t * (pw - 2*(knob_r+2)))
            self.bg_canvas.create_oval(knob_x-knob_r, py+ph//2-knob_r,
                                       knob_x+knob_r, py+ph//2+knob_r,
                                       fill="#ffffff", outline="")
            y += 24
        self.bg_canvas.create_line(left+8, y+2, right-8, y+2, fill=theme["panel_border"], width=1)
        y += 16
        self.bg_canvas.create_text(left+8, y, text=self._caps("Connected Services"),
                                   fill=theme["muted"], font=self.typo["label_soft"], anchor="nw")
        y += 18
        for name, key in [("Deepgram", "DEEPGRAM_API_KEY"), ("ElevenLabs", "ELEVENLABS_API_KEY"),
                          ("Gemini", "GEMINI_API_KEY"), ("Google Cal", "GOOGLE_CLIENT_ID"),
                          ("SerpAPI", "SERPAPI_KEY")]:
            ok = self._check_service(key)
            dc = theme["service_ok"] if ok else theme["service_off"]
            self.bg_canvas.create_oval(left+8, y+3, left+16, y+11, fill=dc, outline="")
            self.bg_canvas.create_text(left+22, y, text=name, fill=theme["text"],
                                       font=self.typo["micro"], anchor="nw")
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

    def _reset_reasoning_chain(self):
        now = time.monotonic()
        base = [("Classify intent","Waiting for request"),("Extract constraints","Waiting for request"),
                ("Route to agent","Waiting for request"),("Execute task","Waiting for request"),
                ("Generate response","Waiting for request")]
        self.state.reasoning_steps = [{"id":i+1,"label":l,"status":"pending","summary":s}
                                       for i,(l,s) in enumerate(base)]
        self.state.reasoning_transition_at = [now]*len(self.state.reasoning_steps)
        self.state.reasoning_active_index = -1
        self.state.reasoning_last_event = "idle"

    def _set_reasoning_step(self, index, status, summary=None, label=None):
        if index < 0 or index >= len(self.state.reasoning_steps): return
        step = self.state.reasoning_steps[index]
        if label: step["label"] = label[:30]
        if summary: step["summary"] = summary[:44]
        if step["status"] != status:
            step["status"] = status
            self.state.reasoning_transition_at[index] = time.monotonic()
        if status == "active": self.state.reasoning_active_index = index

    def _activate_reasoning_step(self, index, summary=None, label=None):
        for i in range(index): self._set_reasoning_step(i, "complete")
        for i in range(index+1, len(self.state.reasoning_steps)):
            if self.state.reasoning_steps[i]["status"] != "complete":
                self._set_reasoning_step(i, "pending")
        self._set_reasoning_step(index, "active", summary=summary, label=label)

    def _complete_reasoning_step(self, index, summary=None):
        self._set_reasoning_step(index, "complete", summary=summary)
        if self.state.reasoning_active_index == index: self.state.reasoning_active_index = -1

    def _safe_agent_name(self, agent):
        return agent if agent in {"BRAIN","SHOPPING","CALENDAR","RESEARCH","GENERAL"} else "GENERAL"

    def _sync_reasoning_status(self):
        from agent import AGENT_ORDER
        current = (self.state.agent_focus, self.state.agent_phase)
        if current == self._last_agent_status: return
        self._last_agent_status = current
        focus, phase = current
        focus = self._safe_agent_name(focus)
        phase = (phase or "").lower()
        if not self._reasoning_initialized_for_turn: return
        if focus == "BRAIN":
            if self.state.reasoning_steps[0]["status"] in ("pending","active"):
                self._activate_reasoning_step(0, summary="Classifying user intent")
                self._complete_reasoning_step(0, summary="Intent identified")
            if self.state.reasoning_steps[1]["status"] in ("pending","active"):
                self._activate_reasoning_step(1, summary="Extracting user constraints")
                if phase in {"thinking","routing"}:
                    self._complete_reasoning_step(1, summary="Constraints extracted")
            if self.state.reasoning_steps[2]["status"] != "complete":
                self._activate_reasoning_step(2, summary="Selecting best specialist agent")
        elif focus in AGENT_ORDER and focus != "BRAIN":
            self._complete_reasoning_step(2, summary=f"Routed to {focus} agent")
            self._activate_reasoning_step(3, summary=f"Executing task with {focus} agent")

    def _draw_reasoning_chain(self, left, right, top, bottom):
        theme = self._theme()
        pulse = (math.sin(time.monotonic() * 6.0) + 1.0) / 2.0
        self._rounded_rect(left+1,top+3,right+1,bottom+3,radius=14,fill=theme["reason_shadow"],outline="")
        self._rounded_rect(left,top,right,bottom,radius=14,fill=theme["reason_panel"],outline=theme["reason_edge"])
        self._rounded_rect(left+1,top+1,right-1,top+30,radius=12,
                           fill=self._lerp_color(theme["reason_panel"],theme["reason_glass_hi"],0.22),outline="")
        completed_count = sum(1 for st in self.state.reasoning_steps if st["status"]=="complete")
        total_steps = len(self.state.reasoning_steps)
        self.bg_canvas.create_text(left+12,top+10,text=self._caps("Reasoning Flow"),
                                   fill=theme["reason_title"],font=self.typo["label"],anchor="nw")
        cc = theme["reason_active"] if completed_count>0 else theme["reason_subtitle"]
        self.bg_canvas.create_text(right-10,top+10,text=f"{completed_count} / {total_steps}",
                                   fill=cc,font=self.typo["mono_tiny"],anchor="ne")
        self.bg_canvas.create_line(left+10,top+32,right-10,top+32,fill=theme["reason_connector"],width=1)
        node_x, title_x = left+22, left+42
        start_y = top+50
        step_gap = min(46, max(36, (bottom-start_y-10)//max(1,total_steps-1)))
        progress_y = start_y + max(0,completed_count-1)*step_gap
        if 0 <= self.state.reasoning_active_index < total_steps:
            i = self.state.reasoning_active_index
            elapsed = time.monotonic()-self.state.reasoning_transition_at[i]
            progress_y = start_y+i*step_gap+min(step_gap*0.55,elapsed*70)
        rail_bottom = start_y+step_gap*(total_steps-1)
        self.bg_canvas.create_line(node_x,start_y,node_x,rail_bottom,fill=theme["reason_connector"],width=2)
        self.bg_canvas.create_line(node_x,start_y,node_x,min(rail_bottom,int(progress_y)),
                                   fill=theme["reason_active"],width=4)
        for i, step in enumerate(self.state.reasoning_steps):
            y = start_y+i*step_gap
            row_top,row_bottom = y-15,y+22
            self.reasoning_row_hitboxes.append((left+10,row_top,right-10,row_bottom))
            hovered = self.reasoning_hover_index==i
            status = step["status"]
            if status=="active":
                self._rounded_rect(left+10,row_top,right-10,row_bottom,radius=8,
                                   fill=self._lerp_color(theme["reason_panel"],theme["reason_active"],0.09),
                                   outline=self._lerp_color(theme["reason_panel"],theme["reason_active"],0.35),width=1)
            elif hovered:
                self._rounded_rect(left+10,row_top,right-10,row_bottom,radius=8,
                                   fill=self._lerp_color(theme["reason_panel"],theme["reason_glass_hi"],0.14),outline="")
            if status=="complete":
                self.bg_canvas.create_oval(node_x-8,y-8,node_x+8,y+8,
                                           fill=theme["reason_complete"],outline=theme["reason_complete"])
                self.bg_canvas.create_text(node_x,y,text="✓",fill="#ffffff",
                                           font=(self.font_mono,9,"bold"),anchor="center")
            elif status=="active":
                glow_r = 11+int(4*pulse)
                self.bg_canvas.create_oval(node_x-glow_r,y-glow_r,node_x+glow_r,y+glow_r,
                                           fill="",outline=theme["reason_active"],width=2)
                self.bg_canvas.create_oval(node_x-8,y-8,node_x+8,y+8,
                                           fill=theme["reason_active"],outline=theme["reason_active"])
                self.bg_canvas.create_oval(node_x-3,y-3,node_x+3,y+3,fill="#ffffff",outline="")
            else:
                self.bg_canvas.create_oval(node_x-8,y-8,node_x+8,y+8,
                                           fill=theme["reason_panel"],outline=theme["reason_pending_outline"],width=2)
                self.bg_canvas.create_text(node_x,y,text=str(i+1),fill=theme["reason_pending_outline"],
                                           font=(self.font_mono,8,"bold"),anchor="center")
            if status=="active":
                tc=theme["reason_active"]; sc=self._lerp_color(theme["reason_row_subtext"],theme["reason_active"],0.35)
            elif status=="complete":
                tc=self._lerp_color(theme["reason_row_text"],theme["reason_active"],0.35) if hovered else theme["reason_row_text"]
                sc=theme["reason_row_subtext"]
            else:
                tc=self._lerp_color(theme["reason_row_subtext"],theme["reason_active"],0.35) if hovered else theme["reason_row_subtext"]
                sc=theme["reason_row_subtext"]
            self.bg_canvas.create_text(title_x,y-10,text=step["label"][:28],fill=tc,font=self.typo["section"],anchor="nw")
            self.bg_canvas.create_text(title_x,y+9,text=step.get("summary","")[:42],fill=sc,
                                       font=(self.font_ui,10,"normal"),anchor="nw",
                                       width=max(90,right-title_x-14),justify="left")