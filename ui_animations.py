import math
import random
import re
import textwrap
import time


class AnimationMixin:
    """All animation tick methods and response formatting."""

    # ── agent flash ──

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
            self.root.after(self.motion["agent_flash_ms"], self._tick_agent_flash)

    # ── mic level ──

    def _start_mic_level_loop(self):
        self._tick_mic_level()

    def _tick_mic_level(self):
        if self.state.listening and not self.state.is_speaking:
            target = random.uniform(0.1, 0.9) if self.state.live_transcript else random.uniform(0.02, 0.3)
            self.mic_level_smooth += (target - self.mic_level_smooth) * 0.20
        else:
            self.mic_level_smooth *= 0.84
        self.mic_level_job = self.root.after(self.motion["mic_ms"], self._tick_mic_level)

    # ── waveform ──

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

        self.waveform_amp += (self.waveform_amp_target - self.waveform_amp) * 0.12
        self.waveform_speed += (self.waveform_speed_target - self.waveform_speed) * 0.12
        self.waveform_phase = (self.waveform_phase + self.waveform_speed) % (math.pi * 2)

        profile = [0.52, 0.74, 1.0, 0.74, 0.52]
        delays = [0.44, 0.24, 0.0, 0.24, 0.44]
        for i in range(5):
            wave = (math.sin(self.waveform_phase - delays[i]) + 1.0) / 2.0
            secondary = (math.sin((self.waveform_phase * 1.8) - delays[i] * 1.6) + 1.0) / 2.0
            self.waveform_noise[i] += random.uniform(-0.007, 0.007)
            self.waveform_noise[i] = max(-0.06, min(0.06, self.waveform_noise[i]))
            organic = 0.68 * wave + 0.32 * secondary
            level = 0.18 + self.waveform_amp * profile[i] * organic + self.waveform_noise[i]
            self.waveform_bars[i] = max(0.12, min(1.0, level))

        self.redraw()
        self.waveform_job = self.root.after(self.motion["waveform_ms"], self._tick_waveform)

    # ── gradient ──

    def _start_gradient_loop(self):
        self._tick_gradient()

    def _tick_gradient(self):
        self.gradient_phase = (self.gradient_phase + 0.006) % (math.pi * 2)
        self.redraw()
        self.gradient_job = self.root.after(self.motion["gradient_ms"], self._tick_gradient)

    # ── thinking ──

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
        self.thinking_job = self.root.after(self.motion["thinking_ms"], self._tick_thinking)

    # ── AI response typing animation ──

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

    def _extract_research_title(self, response, fallback):
        text = re.sub(r"\s+", " ", response).strip()
        for raw in re.split(r"[\n.!?]", text):
            line = re.sub(r"^[\-\u2022\d\.)\s]+", "", raw).strip()
            if len(line) >= 8:
                return line[:90]
        return fallback.strip()[:90]

    def _start_ai_response_animation(self, response):
        self.ai_animation_target = self._format_ai_response(response)
        self.ai_render_text = ""
        self.ai_animation_index = 0
        self._cursor_visible = True
        if self.ai_animation_job:
            self.root.after_cancel(self.ai_animation_job)
            self.ai_animation_job = None
        if self._cursor_job:
            self.root.after_cancel(self._cursor_job)
            self._cursor_job = None
        self._tick_cursor_blink()
        self._tick_ai_response_animation()

    def _tick_cursor_blink(self):
        self._cursor_visible = not self._cursor_visible
        self.redraw()
        self._cursor_job = self.root.after(530, self._tick_cursor_blink)

    def _tick_ai_response_animation(self):
        if self.ai_animation_index >= len(self.ai_animation_target):
            self._complete_reasoning_step(4, summary="Response ready")
            self.ai_animation_job = None
            if self._cursor_job:
                self.root.after_cancel(self._cursor_job)
                self._cursor_job = None
            self._cursor_visible = False
            self.redraw()
            return

        next_char = self.ai_animation_target[self.ai_animation_index]
        if next_char in {".", "!", "?"}:
            step, delay = 1, self.motion["typing_pause_ms"]
        elif next_char in {",", ";", ":"}:
            step, delay = 1, int(self.motion["typing_pause_ms"] * 0.6)
        elif next_char == "\n":
            step, delay = 1, int(self.motion["typing_pause_ms"] * 0.4)
        else:
            step, delay = self.motion["typing_step"], self.motion["typing_ms"]

        self.ai_animation_index = min(
            self.ai_animation_index + step, len(self.ai_animation_target)
        )
        self.ai_render_text = self.ai_animation_target[: self.ai_animation_index]
        self._sync_reasoning_status()
        self.redraw()
        self.ai_animation_job = self.root.after(delay, self._tick_ai_response_animation)

    # ── pulse ──

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
        self.pulse_job = self.root.after(self.motion["pulse_ms"], self._pulse_tick)