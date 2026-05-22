"""Theme, palette, and shared color helpers for the OpenSight canvas UI."""
import os
import math
import time


class ThemeMixin:
    """Color, theme, and style helpers shared across all draw methods."""

    def _caps(self, text):
        """Uppercase a label for canvas headings."""
        return str(text).upper()

    def _check_service(self, key):
        """Check whether an environment service key is set."""
        return bool(os.getenv(key, "").strip())

    def _theme(self) -> dict:
        """Return the active light or dark theme palette."""
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
                "dot_pattern": "#1e3a5c", "powered_by": "#5C728A",
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
            "dot_pattern": "#c8d8e8", "powered_by": "#b8d0de",
            "reason_complete": "#3a9a5a", "reason_active": "#4a89b0",
            "reason_pending": "#8aa5b5", "reason_connector": "#c6d8e3",
            "reason_panel": "#f3f9fd",
            "reason_title": "#1d455d", "reason_subtitle": "#62869b",
            "reason_row_text": "#1b3f55", "reason_row_subtext": "#6d8fa2",
            "reason_edge": "#bfd5e2", "reason_shadow": "#bfd3df",
            "reason_glass_hi": "#ffffff", "reason_pending_outline": "#91adbd",
        }

    def _lerp_color(self, c1, c2, t):
        """Blend two hex colors by interpolation factor t."""
        def h2r(h):
            h = h.lstrip("#")
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        r1, g1, b1 = h2r(c1)
        r2, g2, b2 = h2r(c2)
        return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

    def _orb_color_for_agent(self):
        """Return orb colors for the current active agent."""
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

    def _orb_label(self):
        """Return the current orb status label."""
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

    def _agent_card_colors(self, agent, active):
        """Return the color palette for an agent card."""
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

    def _agent_glow_color(self, agent):
        """Return the glow color for an active agent card."""
        dark = self.state.ui_mode == "dark"
        d = {"BRAIN": "#0a1e3a", "SHOPPING": "#0a1e12", "CALENDAR": "#1e1400",
             "RESEARCH": "#120a28", "GENERAL": "#0a1420"}
        l = {"BRAIN": "#c8e0f4", "SHOPPING": "#c8ecd6", "CALENDAR": "#f0e0b0",
             "RESEARCH": "#d8ccf4", "GENERAL": "#c8d8e8"}
        return (d if dark else l).get(agent, "#0b1826" if dark else "#e8f2f8")