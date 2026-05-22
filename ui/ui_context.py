"""Context tab rendering and document management for the OpenSight UI."""
import tkinter as tk

_TITLE_PH = "Document title..."
_SUMMARY_PH = "Add context, notes, or key facts..."


class ContextMixin:
    """Context tab — About You pills (removable), Recent bubbles, Documents."""

    def _draw_context_panel(self, left, right, h):
        """Draw the context sidebar and its sections."""
        theme = self._theme()
        mid = (left + right) // 2

        self.bg_canvas.create_text(mid, 58, text=self._caps("Context"),
                                   fill=theme["accent"], font=self.typo["label"], anchor="center")

        mem_prefs, mem_topics, mem_last_agent, mem_last_query = {}, [], "", ""
        try:
            from memory import SessionMemory
            m = SessionMemory.load()
            mem_prefs = m.preferences or {}
            mem_topics = (m.entities or {}).get("topics", [])
            mem_last_agent = m.last_agent or ""
            mem_last_query = m.last_query or ""
        except Exception:
            pass

        status_text = (f"Last: {mem_last_agent.capitalize()} · {mem_last_query[:28]}"
                       if mem_last_agent and mem_last_query
                       else (f"Last agent: {mem_last_agent}" if mem_last_agent
                             else "No activity yet this session"))
        self.bg_canvas.create_text(mid, 73, text=status_text,
                                   fill=theme.get("meta", theme["muted"]),
                                   font=self.typo["mono_micro"], anchor="center")
        self.bg_canvas.create_line(left + 10, 86, right - 10, 86,
                                   fill=theme["panel_border"], width=1, dash=(4, 4))

        sections = [
            ("about",     "About You"),
            ("recent",    "Recent Context"),
            ("documents", f"Documents  ({len(self.context_documents)})"),
        ]
        y = 94

        for key, title in sections:
            is_open = self.context_open_section == key
            header_h = 32
            x1, x2 = left + 6, right - 6
            self.context_section_hitboxes[key] = (x1, y, x2, y + header_h)

            self._rounded_rect(x1+1, y+2, x2+1, y+header_h+2, radius=10,
                               fill=self._lerp_color(theme["reason_shadow"], theme["panel"], 0.65), outline="")
            anim_t = self.context_section_anim.get(key, 0.0)
            header_fill = self._lerp_color(theme["panel"],
                                           self._lerp_color(theme["panel"], theme["tab_active"], 0.65), anim_t)
            self._rounded_rect(x1, y, x2, y+header_h, radius=9, fill=header_fill,
                               outline=theme["tab_border_active"] if is_open else theme["panel_border"])
            if is_open:
                self.bg_canvas.create_rectangle(x1, y+8, x1+3, y+header_h-8,
                                                fill=theme["accent"], outline="")
            self.bg_canvas.create_text(x1+13, y+8, text=title,
                                       fill=theme["tab_text_active"] if is_open else theme["text"],
                                       font=self.typo["label"], anchor="nw")
            self.bg_canvas.create_text(x2-10, y+8, text="▾" if is_open else "▸",
                                       fill=theme["accent"] if is_open else theme["muted"],
                                       font=self.typo["label"], anchor="ne")
            y += header_h + 5

            if is_open and anim_t > 0.05:
                max_body_h = max(80, (h - 52) - y)
                body_h = min(310, max_body_h)
                self._rounded_rect(x1+1, y+3, x2+1, y+body_h+3, radius=12,
                                   fill=self._lerp_color(theme["reason_shadow"], theme["panel"], 0.68), outline="")
                self._rounded_rect(x1, y, x2, y+body_h, radius=11,
                                   fill=self._lerp_color(theme["panel"], theme["tab_inactive"], 0.28),
                                   outline=theme["panel_border"])
                self._rounded_rect(x1+1, y+1, x2-1, y+22, radius=10,
                                   fill=self._lerp_color(theme["panel"],
                                                         self._lerp_color(theme["tab_inactive"], theme["panel"], 0.45),
                                                         anim_t), outline="")
                if key == "about":
                    self._draw_context_about_content(x1, y, x2, body_h, theme, mem_prefs, mem_topics)
                elif key == "recent":
                    self._draw_context_recent_content(x1, y, x2, body_h, theme)
                elif key == "documents":
                    self._draw_documents_section_content(x1, y, x2, body_h, theme)
                y += body_h + 7

            if y > h - 48:
                break

        self.bg_canvas.create_text(mid, h-16, text="Resets on app close",
                                   fill=theme.get("meta", theme["muted"]),
                                   font=self.typo["mono_tiny"], anchor="center")

    def _tick_context_section_anim(self):
        """Animate the open context section transition."""
        key = self.context_open_section
        changed = False
        for k in ("about", "recent", "documents"):
            target = 1.0 if k == key else 0.0
            current = self.context_section_anim.get(k, 0.0)
            diff = target - current
            if abs(diff) > 0.02:
                self.context_section_anim[k] = current + diff * 0.28
                changed = True
            else:
                self.context_section_anim[k] = target
        if changed:
            self.redraw()
            self.context_anim_job = self.root.after(16, self._tick_context_section_anim)
        else:
            self.context_anim_job = None

    # ── About You ──────────────────────────────────────────────────────────────

    def _draw_context_about_content(self, x1, y, x2, body_h, theme, mem_prefs, mem_topics):
        """Draw saved preferences and topic pills."""
        pad = 12
        cy = y + pad + 4
        inner_w = x2 - x1 - pad * 2

        name = self.state.username.strip() if self.state.username else "—"
        for label, val in [("NAME", name), ("SPEED", self.voice_speed.capitalize()),
                           ("THEME", self.state.ui_mode.capitalize())]:
            self.bg_canvas.create_text(x1+pad, cy, text=label,
                                       fill=theme["muted"], font=self.typo["mono_label"], anchor="nw")
            self.bg_canvas.create_text(x2-pad, cy, text=val,
                                       fill=theme["text"], font=self.typo["label"], anchor="ne")
            cy += 18

        cy += 4
        self.bg_canvas.create_line(x1+pad, cy, x2-pad, cy, fill=theme["panel_border"], width=1)
        cy += 10

        self.bg_canvas.create_text(x1+pad, cy, text="LEARNED  ·  click × to remove",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")
        cy += 16

        # build pill list
        pills = []
        if mem_prefs.get("budget"):
            pills.append((f"${mem_prefs['budget']} budget", theme["reason_active"], "budget", None))
        for a in (mem_prefs.get("allergies") or [])[:4]:
            pills.append((f"no {a}", theme["service_off"], "allergy", a))
        for d in (mem_prefs.get("diet") or [])[:3]:
            pills.append((d, theme["reason_complete"], "diet", d))
        for t in (mem_topics or [])[-5:]:
            pills.append((t, theme["accent"], "topic", t))

        if not pills:
            self.bg_canvas.create_text(x1+pad, cy,
                                       text="Nothing learned yet.\nSpeak a request to start.",
                                       fill=theme.get("text_secondary", theme["muted"]),
                                       font=self.typo["micro"], anchor="nw",
                                       width=inner_w, justify="left")
            return

        # ensure dict exists
        if not hasattr(self, "pill_remove_hitboxes"):
            self.pill_remove_hitboxes = {}

        pill_x = x1 + pad
        pill_h = 20
        pill_gap_x, pill_gap_y = 5, 6
        pill_pad_x = 7
        x_btn_w = 14  # width of the × button inside the pill
        max_pills_shown = 12
        shown = 0
        leftover = 0

        for text, color, kind, value in pills:
            if shown >= max_pills_shown:
                leftover += 1
                continue
            pill_text_w = len(text) * 6 + pill_pad_x * 2
            pill_w = pill_text_w + x_btn_w + 2

            if pill_x + pill_w > x2 - pad:
                pill_x = x1 + pad
                cy += pill_h + pill_gap_y
            if cy + pill_h > y + body_h - 10:
                leftover += 1
                continue

            pill_bg = self._lerp_color(theme["panel"], color, 0.18)
            pill_outline = self._lerp_color(theme["panel"], color, 0.45)
            self._rounded_rect(pill_x, cy, pill_x+pill_w, cy+pill_h,
                               radius=10, fill=pill_bg, outline=pill_outline)
            self.bg_canvas.create_text(pill_x+pill_pad_x, cy+3, text=text,
                                       fill=color, font=self.typo["mono_tiny"], anchor="nw")
            # × remove button inside pill
            x_btn_x1 = pill_x + pill_text_w
            self.bg_canvas.create_text(x_btn_x1 + x_btn_w//2, cy + pill_h//2,
                                       text="×", fill=self._lerp_color(color, "#ffffff", 0.3),
                                       font=(self.font_mono, 9, "bold"), anchor="center")
            # store hitbox for the × zone only
            self.pill_remove_hitboxes[(kind, value)] = (
                x_btn_x1, cy, pill_x+pill_w, cy+pill_h
            )

            pill_x += pill_w + pill_gap_x
            shown += 1

        if leftover > 0:
            cy += pill_h + pill_gap_y
            self.bg_canvas.create_text(x1+pad, cy, text=f"+ {leftover} more",
                                       fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")

    def remove_learned_item(self, kind: str, value):
        """Called from on_canvas_click when a pill × is hit."""
        try:
            from memory import SessionMemory
            m = SessionMemory.load()
            if kind == "budget":
                m.preferences.pop("budget", None)
            elif kind == "allergy":
                allergies = m.preferences.get("allergies", [])
                m.preferences["allergies"] = [a for a in allergies if a != value]
            elif kind == "diet":
                diets = m.preferences.get("diet", [])
                m.preferences["diet"] = [d for d in diets if d != value]
            elif kind == "topic":
                topics = m.entities.get("topics", [])
                m.entities["topics"] = [t for t in topics if t != value]
            m.save()
        except Exception as e:
            print(f"[context] remove pill error: {e}")
        self.redraw()

    # ── Recent Context ─────────────────────────────────────────────────────────

    def _draw_context_recent_content(self, x1, y, x2, body_h, theme):
        """Draw the recent conversation bubbles."""
        pad = 10
        cy = y + pad + 2
        s = self.state

        if not s.transcript_history:
            self.bg_canvas.create_text((x1+x2)//2, y+body_h//2,
                                       text="No conversation yet.\nStart speaking to see turns here.",
                                       fill=theme.get("text_secondary", theme["muted"]),
                                       font=self.typo["micro"], anchor="center",
                                       width=x2-x1-pad*2, justify="center")
            return

        max_bubble_w = int((x2-x1) * 0.84)
        for entry in s.transcript_history[-6:]:
            if cy > y + body_h - 28:
                break
            if entry.startswith("You:"):
                is_user, text = True, entry[4:].strip()
            elif entry.startswith("OpenSight:"):
                is_user, text = False, entry[10:].strip()
            else:
                is_user, text = False, entry.strip()

            if len(text) > 62:
                text = text[:60] + "…"

            bubble_w = min(max_bubble_w, len(text)*6+20)
            bubble_h = 22

            if is_user:
                bx2 = x2 - pad
                bx1 = bx2 - bubble_w
                fill = self._lerp_color(theme["panel"], theme["accent"], 0.22)
                outline = self._lerp_color(theme["panel"], theme["accent"], 0.50)
                text_color = theme["tab_text_active"]
                text_x, text_anchor = bx2-8, "ne"
            else:
                bx1 = x1 + pad
                bx2 = bx1 + bubble_w
                fill = self._lerp_color(theme["panel"], theme["tab_inactive"], 0.55)
                outline = theme["panel_border"]
                text_color = theme["text"]
                text_x, text_anchor = bx1+8, "nw"

            self._rounded_rect(bx1, cy, bx2, cy+bubble_h, radius=9, fill=fill, outline=outline)
            self.bg_canvas.create_text(text_x, cy+4, text=text, fill=text_color,
                                       font=self.typo["micro"], anchor=text_anchor,
                                       width=bubble_w-16)
            cy += bubble_h + 6

    # ── Documents ──────────────────────────────────────────────────────────────

    def _draw_documents_section_content(self, x1, y, x2, body_h, theme):
        """Draw the document editor and saved notes list."""
        pad = 10
        inner_w = max(80, (x2-x1) - pad*2)
        self._ensure_context_doc_inputs(theme)

        # ── input zone ──
        title_h, summary_h, btn_h = 26, 34, 28
        iz_inner_pad = 10
        iz_h = iz_inner_pad + 13 + title_h + 8 + 13 + summary_h + 10 + btn_h + iz_inner_pad
        iz_x1, iz_x2 = x1+pad, x2-pad
        iz_y1 = y + pad

        self._rounded_rect(iz_x1, iz_y1, iz_x2, iz_y1+iz_h, radius=10,
                           fill=self._lerp_color(theme["input_bg"], theme["panel"], 0.3),
                           outline=theme["input_border"])

        cy = iz_y1 + iz_inner_pad

        self.bg_canvas.create_text(iz_x1+6, cy, text="TITLE",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")
        cy += 13
        self.bg_canvas.create_rectangle(iz_x1+4, cy, iz_x2-4, cy+title_h,
                                        fill=theme["input_bg"], outline="")
        self.bg_canvas.create_line(iz_x1+4, cy+title_h, iz_x2-4, cy+title_h,
                                   fill=theme["accent"], width=1)
        self.bg_canvas.create_window(iz_x1+6, cy+2, width=inner_w-12,
                                     height=title_h-4, anchor="nw",
                                     window=self.context_doc_title_entry)
        cy += title_h + 8

        self.bg_canvas.create_text(iz_x1+6, cy, text="CONTEXT / NOTES",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="nw")
        cy += 13
        self.bg_canvas.create_rectangle(iz_x1+4, cy, iz_x2-4, cy+summary_h,
                                        fill=theme["input_bg"], outline="")
        self.bg_canvas.create_line(iz_x1+4, cy+summary_h, iz_x2-4, cy+summary_h,
                                   fill=theme["accent"], width=1)
        self.bg_canvas.create_window(iz_x1+6, cy+2, width=inner_w-12,
                                     height=summary_h-4, anchor="nw",
                                     window=self.context_doc_note_entry)
        cy += summary_h + 10

        # full-width Add button
        ax1, ax2 = iz_x1+4, iz_x2-4
        self.context_add_hitbox = (ax1, cy, ax2, cy+btn_h)
        self._rounded_rect(ax1, cy, ax2, cy+btn_h, radius=8,
                           fill=theme["accent"], outline=theme["accent"])
        self.bg_canvas.create_text((ax1+ax2)//2, cy+7, text="+ Add Document",
                                   fill="#ffffff", font=self.typo["label"], anchor="n")

        # ── library zone ──
        lib_y = iz_y1 + iz_h + 10
        doc_count = len(self.context_documents)
        mid_x = (x1+x2)//2

        # divider with count
        self.bg_canvas.create_line(x1+pad, lib_y+6, mid_x-62, lib_y+6,
                                   fill=theme["panel_border"], width=1)
        self.bg_canvas.create_text(mid_x, lib_y, text=f"YOUR DOCS  ·  {doc_count}",
                                   fill=theme["muted"], font=self.typo["mono_tiny"], anchor="n")
        self.bg_canvas.create_line(mid_x+62, lib_y+6, x2-pad-38, lib_y+6,
                                   fill=theme["panel_border"], width=1)

        # ghost "Clear all" link
        if doc_count > 0:
            clr_x = x2 - pad - 2
            self.context_clear_docs_hitbox = (clr_x-38, lib_y, clr_x, lib_y+14)
            self.bg_canvas.create_text(clr_x, lib_y, text="Clear all",
                                       fill=theme.get("meta", theme["muted"]),
                                       font=self.typo["mono_tiny"], anchor="ne")

        lib_y += 18

        if not self.context_documents:
            self.bg_canvas.create_text(mid_x, lib_y+16,
                                       text="No documents yet.\nFill in a title and press Add.",
                                       fill=theme.get("text_secondary", theme["muted"]),
                                       font=self.typo["micro"], anchor="n",
                                       width=inner_w, justify="center")
            return

        accent_colors = [
            theme["accent"], theme["reason_complete"],
            theme["reason_active"],
            self._lerp_color(theme["accent"], theme["reason_complete"], 0.5),
        ]

        if not hasattr(self, "context_doc_card_hitboxes"):
            self.context_doc_card_hitboxes = {}

        # show most recent 3, newest on top
        max_rows = 3
        start_idx = max(0, len(self.context_documents) - max_rows)
        cy = lib_y

        for display_pos, doc_idx in enumerate(
            range(len(self.context_documents)-1, start_idx-1, -1), 1
        ):
            if cy > y + body_h - 50:
                # show overflow count
                remaining = len(self.context_documents) - (display_pos - 1)
                if remaining > 0:
                    self.bg_canvas.create_text(mid_x, cy+4,
                                               text=f"+ {remaining} more — clear some to see all",
                                               fill=theme["muted"], font=self.typo["mono_tiny"],
                                               anchor="n")
                break

            doc = self.context_documents[doc_idx]
            cx1, cx2 = x1+pad, x2-pad
            card_h = 48
            cy1, cy2 = cy, cy+card_h
            accent_col = accent_colors[doc_idx % len(accent_colors)]
            is_hovered = getattr(self, "context_doc_hover_idx", -1) == doc_idx
            self.context_doc_card_hitboxes[doc_idx] = (cx1, cy1, cx2, cy2)

            # shadow
            self._rounded_rect(cx1+1, cy1+2, cx2+1, cy2+2, radius=10,
                               fill=self._lerp_color(theme["reason_shadow"], theme["panel"], 0.72), outline="")
            # card
            card_fill = self._lerp_color(
                self._lerp_color(theme["panel"], theme["tab_active"], 0.18),
                theme["tab_active"], 0.22 if is_hovered else 0.0)
            self._rounded_rect(cx1, cy1, cx2, cy2, radius=9, fill=card_fill,
                               outline=theme["tab_border_active"] if is_hovered else theme["panel_border"])

            # colored top strip
            strip_h = 3
            self.bg_canvas.create_rectangle(cx1, cy1, cx2, cy1+strip_h,
                                            fill=accent_col, outline="")
            # patch corners of strip back to card fill
            self.bg_canvas.create_rectangle(cx1, cy1+strip_h, cx2, cy1+strip_h+1,
                                            fill=card_fill, outline="")

            title = (doc.get("title") or f"Doc {display_pos}")[:30]
            summary = (doc.get("summary") or "")[:52]
            self.bg_canvas.create_text(cx1+10, cy1+strip_h+4, text=title,
                                       fill=theme["text"], font=self.typo["section"], anchor="nw")
            if summary:
                self.bg_canvas.create_text(cx1+10, cy1+strip_h+20, text=summary,
                                           fill=theme.get("text_secondary", theme["muted"]),
                                           font=self.typo["mono_tiny"], anchor="nw",
                                           width=max(60, cx2-cx1-70), justify="left")

            # delete — always visible, small, right-aligned
            del_w, del_h = 40, 18
            del_x1 = cx2 - del_w - 6
            del_y1 = cy2 - del_h - 5
            del_x2, del_y2 = del_x1+del_w, del_y1+del_h
            self.context_doc_delete_hitboxes[doc_idx] = (del_x1, del_y1, del_x2, del_y2)
            self._rounded_rect(del_x1, del_y1, del_x2, del_y2, radius=5,
                               fill=self._lerp_color(theme["panel"], theme["service_off"], 0.12 if is_hovered else 0.06),
                               outline=self._lerp_color(theme["panel_border"], theme["service_off"], 0.5 if is_hovered else 0.25))
            self.bg_canvas.create_text((del_x1+del_x2)//2, del_y1+3, text="✕ del",
                                       fill=theme["service_off"] if is_hovered else theme["muted"],
                                       font=self.typo["mono_tiny"], anchor="n")

            cy += card_h + 6

    # ── input widgets ──────────────────────────────────────────────────────────

    def _ensure_context_doc_inputs(self, theme):
        """Create the document input widgets when needed."""
        if self.context_doc_title_entry is None:
            self.context_doc_title_entry = tk.Entry(self.bg_canvas, font=self.typo["body"], relief="flat")
            self._setup_entry_placeholder(self.context_doc_title_entry, _TITLE_PH, theme)
            self.context_doc_title_entry.bind("<Return>", self._add_context_document_from_inputs)
        if self.context_doc_note_entry is None:
            self.context_doc_note_entry = tk.Entry(self.bg_canvas, font=self.typo["micro"], relief="flat")
            self._setup_entry_placeholder(self.context_doc_note_entry, _SUMMARY_PH, theme)
            self.context_doc_note_entry.bind("<Return>", self._add_context_document_from_inputs)
        for entry, ph in ((self.context_doc_title_entry, _TITLE_PH),
                          (self.context_doc_note_entry, _SUMMARY_PH)):
            is_ph = entry.get() in ("", ph)
            entry.configure(bg=theme["input_bg"],
                            fg=theme["muted"] if is_ph else theme["input_text"],
                            insertbackground=theme["input_text"],
                            highlightthickness=0, relief="flat", bd=0)

    def _setup_entry_placeholder(self, entry, placeholder, theme):
        """Attach placeholder behavior to an entry widget."""
        entry.insert(0, placeholder)
        entry.configure(fg=theme["muted"])
        def _fi(e, _e=entry, _p=placeholder):
            if _e.get() == _p:
                _e.delete(0, tk.END)
                try: _e.configure(fg=self._theme()["input_text"])
                except Exception: pass
        def _fo(e, _e=entry, _p=placeholder):
            if not _e.get().strip():
                _e.insert(0, _p)
                try: _e.configure(fg=self._theme()["muted"])
                except Exception: pass
        entry.bind("<FocusIn>", _fi)
        entry.bind("<FocusOut>", _fo)

    def _destroy_context_doc_inputs(self):
        """Destroy the document input widgets if they exist."""
        if self.context_doc_title_entry is not None:
            self.context_doc_title_entry.destroy()
            self.context_doc_title_entry = None
        if self.context_doc_note_entry is not None:
            self.context_doc_note_entry.destroy()
            self.context_doc_note_entry = None

    def _add_context_document_from_inputs(self, event=None):
        """Add a document from the context input fields."""
        title = (self.context_doc_title_entry.get().strip() if self.context_doc_title_entry else "")
        summary = (self.context_doc_note_entry.get().strip() if self.context_doc_note_entry else "")
        if title == _TITLE_PH: title = ""
        if summary == _SUMMARY_PH: summary = ""
        if not title and not summary:
            return "break" if event is not None else None
        if not title:
            title = f"Context {len(self.context_documents)+1}"
        self.context_documents.append({"title": title[:60], "summary": summary[:220]})
        if len(self.context_documents) > 24:
            self.context_documents = self.context_documents[-24:]
        theme = self._theme()
        if self.context_doc_title_entry:
            self.context_doc_title_entry.delete(0, tk.END)
            self.context_doc_title_entry.insert(0, _TITLE_PH)
            self.context_doc_title_entry.configure(fg=theme["muted"])
        if self.context_doc_note_entry:
            self.context_doc_note_entry.delete(0, tk.END)
            self.context_doc_note_entry.insert(0, _SUMMARY_PH)
            self.context_doc_note_entry.configure(fg=theme["muted"])
        self.redraw()
        return "break" if event is not None else None

    def _delete_context_document(self, index):
        """Delete a saved context document by index."""
        if 0 <= index < len(self.context_documents):
            self.context_documents.pop(index)
            self.context_doc_hover_idx = -1
            self.redraw()

    def _clear_context_documents(self):
        """Clear all saved context documents."""
        if self.context_documents:
            self.context_documents = []
            self.context_doc_hover_idx = -1
            self.redraw()