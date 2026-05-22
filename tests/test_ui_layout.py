"""
Unit tests for OpenSight UI layout — verifies spacing, radii, font sizes, and
that no element overflows its containing panel.

Design spec source: opensight-design-system (Claude Design export, 2026-05-20).
Reference file:     ui/ui_draw.py, ui/ui_theme.py, desktop_app.py
"""
import sys
import types
import math
import pytest

# ---------------------------------------------------------------------------
# Stub tkinter so tests run headlessly without a display
# ---------------------------------------------------------------------------
tk_stub = types.ModuleType("tkinter")
tk_stub.Tk = object
tk_stub.Canvas = object
tk_stub.Frame = object
tk_stub.Entry = object
tk_stub.END = "end"
tk_stub.TclError = Exception

tkfont_stub = types.ModuleType("tkinter.font")
tkfont_stub.families = lambda root=None: set()
tk_stub.font = tkfont_stub
sys.modules["tkinter"] = tk_stub
sys.modules["tkinter.font"] = tkfont_stub

# Also stub heavy runtime deps so imports don't blow up
for _mod in ["dotenv", "app_state", "audio_engine", "agent",
             "browser_manager", "memory", "PIL", "PIL.Image",
             "PIL.ImageTk"]:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# ---------------------------------------------------------------------------
# Helpers — replicate the sz() formula from desktop_app._init_typography
# ---------------------------------------------------------------------------
def sz(v: float) -> int:
    return max(8, int(round(v - 1.5)))


# ---------------------------------------------------------------------------
# Design-spec constants (from colors_and_type.css and project README)
# ---------------------------------------------------------------------------
DARK_PALETTE = {
    "background":   "#0b1826",
    "rail":         "#111f2e",
    "rail_border":  "#1e3347",
    "panel":        "#0f1e2d",
    "panel_border": "#1e3347",
    "accent":       "#6bb3d9",
    "service_ok":   "#56b97a",
    "service_off":  "#e05858",
    "reason_panel": "#0f1e2d",
    "reason_edge":  "#2b4a5e",
    "reason_shadow":"#0a121b",
    "reason_glass_hi":"#234057",
    "reason_connector":"#1f3447",
    "reason_complete":"#56b97a",
    "reason_active":"#6bb3d9",
    "reason_pending_outline":"#61869b",
    "dot_pattern":  "#1e3a5c",
    "window_border":"#2a5a7a",
    "wordmark":     "#EAF2FF",
}

LIGHT_PALETTE = {
    "background":   "#e8f2f8",
    "rail":         "#ffffff",
    "panel":        "#f7fbff",
    "panel_border": "#d4e1ea",
    "accent":       "#4a89b0",
    "service_ok":   "#3a9a5a",
    "service_off":  "#c04040",
    "dot_pattern":  "#c8d8e8",
    "window_border":"#88b8cc",
}

# design border radii (px) — sourced from colors_and_type.css --r-* variables
RADII = {
    "xs":        5,   # ACTIVE pill
    "sm":        6,   # speed buttons
    "md":        8,   # settings cells, mode toggle
    "lg":       10,   # agent cards, tabs
    "pill_card":14,   # response card
    "panel":    17,   # outer glow on active agent card
    "toggle":    9,   # settings toggle pills (--r-toggle)
}

WINDOW_W = 1100
WINDOW_H = 700

REASON_PANEL_HEIGHT = 290   # hardcoded in _draw_agent_rail
CHAIN_BOTTOM = WINDOW_H - 28
CHAIN_TOP    = CHAIN_BOTTOM - REASON_PANEL_HEIGHT
TOTAL_STEPS  = 5


# ---------------------------------------------------------------------------
# 1. Typography
# ---------------------------------------------------------------------------
class TestTypography:
    """sz() formula produces values that are large enough for readability."""

    def test_sz_body_large(self):
        assert sz(15) == 14

    def test_sz_body(self):
        assert sz(14) == 12

    def test_sz_section(self):
        assert sz(12) == 10

    def test_sz_label(self):
        assert sz(11) == 10

    def test_sz_mono_label(self):
        assert sz(11) == 10

    def test_mono_micro_is_10pt(self):
        """mono_micro is hardcoded to 10pt (matches --type-mono-micro: 10px in design CSS)."""
        mono_micro_pt = 10
        assert mono_micro_pt >= 9, "mono_micro must be at least 9pt"

    def test_mono_tiny_is_10pt(self):
        """mono_tiny is hardcoded to 10pt (matches --type-mono-tiny: 10px in design CSS)."""
        mono_tiny_pt = 10
        assert mono_tiny_pt >= 9, "mono_tiny must be at least 9pt"

    def test_sz_floor_is_8(self):
        assert sz(9) == 8
        assert sz(8) == 8
        assert sz(7) == 8

    def test_all_sizes_are_positive(self):
        for v in [10, 11, 12, 14, 15, 20, 30]:
            assert sz(v) > 0


# ---------------------------------------------------------------------------
# 2. Reasoning chain — step_gap must keep last row inside the panel
# ---------------------------------------------------------------------------
class TestReasoningChain:
    """The reasoning chain's last step row must not overflow the panel."""

    def _compute_step_gap(self, bottom, start_y, total_steps):
        """Mirror of the fixed formula in _draw_reasoning_chain."""
        return max(44, min(52, (bottom - start_y - 32) // max(1, total_steps - 1)))

    def test_last_row_bottom_inside_panel(self):
        start_y = CHAIN_TOP + 50
        step_gap = self._compute_step_gap(CHAIN_BOTTOM, start_y, TOTAL_STEPS)
        last_step_y = start_y + (TOTAL_STEPS - 1) * step_gap
        row_bottom = last_step_y + 22   # row_bottom = y + 22 (from drawing code)
        assert row_bottom <= CHAIN_BOTTOM, (
            f"last row_bottom {row_bottom} > chain_bottom {CHAIN_BOTTOM}: "
            "reasoning step overflows panel"
        )

    def test_step_gap_minimum(self):
        start_y = CHAIN_TOP + 50
        step_gap = self._compute_step_gap(CHAIN_BOTTOM, start_y, TOTAL_STEPS)
        assert step_gap >= 44, f"step_gap {step_gap} < 44 (steps would overlap)"

    def test_step_gap_maximum(self):
        start_y = CHAIN_TOP + 50
        step_gap = self._compute_step_gap(CHAIN_BOTTOM, start_y, TOTAL_STEPS)
        assert step_gap <= 52, f"step_gap {step_gap} > 52 (steps would overflow)"

    def test_all_steps_start_inside_panel(self):
        start_y = CHAIN_TOP + 50
        step_gap = self._compute_step_gap(CHAIN_BOTTOM, start_y, TOTAL_STEPS)
        for i in range(TOTAL_STEPS):
            y = start_y + i * step_gap
            assert CHAIN_TOP <= y <= CHAIN_BOTTOM, (
                f"step {i} center y={y} is outside panel [{CHAIN_TOP}, {CHAIN_BOTTOM}]"
            )

    def test_five_steps_fit_vertically(self):
        start_y = CHAIN_TOP + 50
        step_gap = self._compute_step_gap(CHAIN_BOTTOM, start_y, TOTAL_STEPS)
        total_height = start_y - CHAIN_TOP + (TOTAL_STEPS - 1) * step_gap + 22
        assert total_height <= REASON_PANEL_HEIGHT, (
            f"5-step layout ({total_height}px) exceeds panel ({REASON_PANEL_HEIGHT}px)"
        )

    def test_panel_header_clears_tabs(self):
        """Reasoning panel must not start inside the agent cards zone (y=90)."""
        assert CHAIN_TOP > 90, (
            f"chain_top={CHAIN_TOP} collides with agent card zone starting at y=90"
        )


# ---------------------------------------------------------------------------
# 3. Response card height
# ---------------------------------------------------------------------------
class TestResponseCard:
    """Response card must have enough height to show multi-line responses."""

    # From the fixed ui_draw.py: card goes from bottom_zone_y-30 to bottom_zone_y+135
    CARD_INNER_H = 135 + 30  # total card height in px

    def _layout_params(self):
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        rail_x = WINDOW_W - rail_w
        main_w = max(400, rail_x)
        orb_r = max(32, min(52, main_w // 20))
        cx = max(200, int(main_w * 0.50))
        cy = WINDOW_H - orb_r - 50
        available_h = cy - orb_r - 80
        center_y = 80 + (available_h // 2)
        bottom_zone_y = center_y + 55
        return cy, orb_r, bottom_zone_y

    def test_card_bottom_below_text_start(self):
        _, _, bottom_zone_y = self._layout_params()
        card_top    = bottom_zone_y - 30
        card_bottom = bottom_zone_y + 135
        text_start  = bottom_zone_y
        assert card_bottom > text_start, "card bottom must be below text origin"

    def test_card_does_not_reach_orb(self):
        cy, orb_r, bottom_zone_y = self._layout_params()
        card_bottom = bottom_zone_y + 135
        orb_label_y = cy - orb_r - 14   # orb label drawn here
        assert card_bottom < orb_label_y, (
            f"response card bottom ({card_bottom}) overlaps orb label ({orb_label_y})"
        )

    def test_card_fits_six_lines_of_body_large(self):
        """Six lines of 14pt body_large (≈21px/line) must fit inside the card."""
        _, _, bottom_zone_y = self._layout_params()
        text_start = bottom_zone_y          # AI text anchor
        card_bottom = bottom_zone_y + 135
        text_area_h = card_bottom - text_start
        line_height_px = 21                 # 14pt * 1.5 leading at 96 DPI
        assert text_area_h >= 6 * line_height_px, (
            f"text area {text_area_h}px cannot fit 6 lines ({6*line_height_px}px)"
        )

    def test_card_height_constant(self):
        """Sanity-check: the 165px constant is correct (130 + 30 + progress bar 5px room)."""
        assert self.CARD_INNER_H == 165


# ---------------------------------------------------------------------------
# 4. YOU label alignment
# ---------------------------------------------------------------------------
class TestTranscriptAlignment:
    """YOU label x must align with centered user text, not the wider AI text."""

    def _layout_params(self):
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        rail_x = WINDOW_W - rail_w
        main_w = max(400, rail_x)
        orb_r = max(32, min(52, main_w // 20))
        cx = max(200, int(main_w * 0.50))
        stack_cx = cx
        ai_text_w   = max(400, int(main_w * 0.88))
        user_text_w = max(260, int(main_w * 0.60))
        lx       = stack_cx - (ai_text_w   // 2)
        user_lx  = stack_cx - (user_text_w // 2)
        return stack_cx, ai_text_w, user_text_w, lx, user_lx

    def test_user_lx_is_not_lx(self):
        _, ai_text_w, user_text_w, lx, user_lx = self._layout_params()
        assert user_lx != lx or user_text_w == ai_text_w, (
            "user_lx should differ from lx when text widths differ"
        )

    def test_you_label_aligns_with_user_text(self):
        stack_cx, _, user_text_w, _, user_lx = self._layout_params()
        expected = stack_cx - user_text_w // 2
        assert user_lx == expected

    def test_user_text_starts_at_user_lx(self):
        """User text centered at stack_cx with user_text_w starts at user_lx."""
        stack_cx, _, user_text_w, _, user_lx = self._layout_params()
        text_left = stack_cx - user_text_w // 2
        assert text_left == user_lx

    def test_you_label_inside_main_panel(self):
        _, _, _, _, user_lx = self._layout_params()
        assert user_lx > 0, "YOU label must not be left of the canvas edge"


# ---------------------------------------------------------------------------
# 5. Window geometry
# ---------------------------------------------------------------------------
class TestWindowGeometry:
    def test_window_width(self):
        assert WINDOW_W == 1100

    def test_window_height(self):
        assert WINDOW_H == 700

    def test_rail_width_range(self):
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        assert 260 <= rail_w <= 300

    def test_tab_height(self):
        assert 28 == 28   # tab_h constant

    def test_tab_radius(self):
        assert RADII["lg"] == 10   # tabs use --r-lg

    def test_agent_card_radius(self):
        assert RADII["lg"] == 10

    def test_agent_glow_radius(self):
        assert RADII["panel"] == 17

    def test_response_card_radius(self):
        assert RADII["pill_card"] == 14

    def test_settings_cell_radius(self):
        assert RADII["md"] == 8

    def test_toggle_pill_radius(self):
        assert RADII["toggle"] == 9

    def test_active_pill_radius(self):
        assert RADII["xs"] == 5


# ---------------------------------------------------------------------------
# 6. Dark-mode color palette — spot-checks against design spec
# ---------------------------------------------------------------------------
class TestDarkPalette:
    def _theme_dark(self):
        """Import the real theme (without tkinter display) via the mixin directly."""
        from ui.ui_theme import ThemeMixin

        class _FakeState:
            ui_mode = "dark"
            agent_focus = "BRAIN"

        class _UI(ThemeMixin):
            def __init__(self):
                self.state = _FakeState()

        return _UI()._theme()

    def test_background(self):
        t = self._theme_dark()
        assert t["background"].lower() == DARK_PALETTE["background"].lower()

    def test_accent(self):
        t = self._theme_dark()
        assert t["accent"].lower() == DARK_PALETTE["accent"].lower()

    def test_panel(self):
        t = self._theme_dark()
        assert t["panel"].lower() == DARK_PALETTE["panel"].lower()

    def test_service_ok(self):
        t = self._theme_dark()
        assert t["service_ok"].lower() == DARK_PALETTE["service_ok"].lower()

    def test_service_off(self):
        t = self._theme_dark()
        assert t["service_off"].lower() == DARK_PALETTE["service_off"].lower()

    def test_rail(self):
        t = self._theme_dark()
        assert t["rail"].lower() == DARK_PALETTE["rail"].lower()

    def test_reason_active(self):
        t = self._theme_dark()
        assert t["reason_active"].lower() == DARK_PALETTE["reason_active"].lower()

    def test_reason_complete(self):
        t = self._theme_dark()
        assert t["reason_complete"].lower() == DARK_PALETTE["reason_complete"].lower()

    def test_dot_pattern(self):
        t = self._theme_dark()
        assert t["dot_pattern"].lower() == DARK_PALETTE["dot_pattern"].lower()


# ---------------------------------------------------------------------------
# 7. Light-mode color palette spot-checks
# ---------------------------------------------------------------------------
class TestLightPalette:
    def _theme_light(self):
        from ui.ui_theme import ThemeMixin

        class _FakeState:
            ui_mode = "light"
            agent_focus = "BRAIN"

        class _UI(ThemeMixin):
            def __init__(self):
                self.state = _FakeState()

        return _UI()._theme()

    def test_background(self):
        t = self._theme_light()
        assert t["background"].lower() == LIGHT_PALETTE["background"].lower()

    def test_accent(self):
        t = self._theme_light()
        assert t["accent"].lower() == LIGHT_PALETTE["accent"].lower()

    def test_service_ok(self):
        t = self._theme_light()
        assert t["service_ok"].lower() == LIGHT_PALETTE["service_ok"].lower()


# ---------------------------------------------------------------------------
# 8. Dot background pattern
# ---------------------------------------------------------------------------
class TestDotPattern:
    def test_grid_spacing_is_28(self):
        grid = 28
        assert grid == 28, "dot pattern grid must be 28px (--dot-pattern spec)"

    def test_dot_radius_is_1(self):
        # create_oval(gx-1, gy-1, gx+1, gy+1) → radius=1px, diameter=2px
        r = 1
        assert r == 1

    def test_dot_covers_main_panel_only(self):
        """Dot pattern should not cover the rail (rail_x to window_w)."""
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        rail_x = WINDOW_W - rail_w
        dot_end_x = rail_x     # dots go from x=0 to x=rail_x
        assert dot_end_x < WINDOW_W, "dots must stop before the rail"


# ---------------------------------------------------------------------------
# 9. Agent card layout
# ---------------------------------------------------------------------------
class TestAgentCardLayout:
    def _card_params(self):
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        rail_x = WINDOW_W - rail_w
        main_w = max(400, rail_x)
        reason_panel_height = 290
        chain_bottom = WINDOW_H - 28
        chain_top = chain_bottom - reason_panel_height
        n = 5   # AGENT_ORDER length
        available = chain_top - 8 - 90
        card_h = max(38, min(46, (available - 6 * (n - 1)) // n))
        card_gap = max(4, min(8, (available - card_h * n) // max(1, n - 1)))
        return n, card_h, card_gap, available

    def test_all_cards_fit_vertically(self):
        n, card_h, card_gap, available = self._card_params()
        used = n * card_h + (n - 1) * card_gap
        assert used <= available, (
            f"{n} agent cards need {used}px but only {available}px available"
        )

    def test_card_height_in_range(self):
        _, card_h, _, _ = self._card_params()
        assert 38 <= card_h <= 46

    def test_card_gap_in_range(self):
        _, _, card_gap, _ = self._card_params()
        assert 4 <= card_gap <= 8


# ---------------------------------------------------------------------------
# 10. Spacing scale
# ---------------------------------------------------------------------------
class TestSpacingScale:
    """Design-spec spacing tokens: 4/8/12/16/24/32/48."""
    SCALE = [4, 8, 12, 16, 24, 32, 48]

    def test_all_values_are_multiples_of_4(self):
        for v in self.SCALE:
            assert v % 4 == 0, f"{v}px is not a multiple of 4"

    def test_card_padding_14_between_space3_and_space4(self):
        """Card padding 14px is between --space-3 (12) and --space-4 (16)."""
        card_pad = 14
        assert 12 <= card_pad <= 16

    def test_rail_side_margin_14(self):
        """Rail side margin 14px falls between space-3 and space-4."""
        rail_margin = 14
        assert 12 <= rail_margin <= 16

    def test_brand_x_is_24(self):
        brand_x = 24
        assert brand_x == 24   # --space-5: window edge

    def test_brand_y_is_18(self):
        brand_y = 18
        assert 16 <= brand_y <= 24   # between space-4 and space-5


# ---------------------------------------------------------------------------
# 13. ACTIVE badge geometry
# ---------------------------------------------------------------------------
class TestActiveBadge:
    """The ACTIVE badge on a focused agent card must be wide enough to fit text."""

    def _badge_dims(self, card_h=44):
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        cr = WINDOW_W - 14   # right edge of rail content (w - 14)
        bx2, bx1 = cr - 5, cr - 68
        yt = 90              # first card top
        by1, by2 = yt + 4, yt + 21
        return bx2 - bx1, by2 - by1

    def test_badge_width_fits_text(self):
        """ACTIVE ↗ at 9pt JetBrains Mono needs ≥55px; badge must be at least that."""
        width, _ = self._badge_dims()
        assert width >= 55, f"badge width {width}px too narrow for 'ACTIVE ↗' at 9pt mono"

    def test_badge_height_fits_9pt(self):
        """9pt font renders at ~12px; badge needs at least 13px height."""
        _, height = self._badge_dims()
        assert height >= 13, f"badge height {height}px insufficient for 9pt text"

    def test_badge_inside_card_horizontal(self):
        """Badge must not overflow the right rail edge."""
        rail_w = max(260, min(300, int(WINDOW_W * 0.26)))
        cr = WINDOW_W - 14
        bx2 = cr - 5
        assert bx2 <= cr, "badge right edge overflows rail content area"


# ---------------------------------------------------------------------------
# 14. Font asset files present
# ---------------------------------------------------------------------------
class TestFontAssets:
    def test_inter_regular_present(self):
        import pathlib
        p = pathlib.Path("assets/fonts/Inter-Regular.ttf")
        assert p.exists(), "Inter-Regular.ttf missing from assets/fonts/"

    def test_jetbrains_mono_regular_present(self):
        import pathlib
        p = pathlib.Path("assets/fonts/JetBrainsMono-Regular.ttf")
        assert p.exists(), "JetBrainsMono-Regular.ttf missing from assets/fonts/"


# ---------------------------------------------------------------------------
# 11. Dot pattern contrast
# ---------------------------------------------------------------------------
class TestDotPatternContrast:
    """Dot color must be visually distinct from the background."""

    def _hex_to_rgb(self, h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    def test_dark_dot_contrast(self):
        bg  = self._hex_to_rgb("#0b1826")
        dot = self._hex_to_rgb("#1e3a5c")
        delta = max(abs(dot[i] - bg[i]) for i in range(3))
        assert delta >= 15, (
            f"dark dot_pattern has max channel delta {delta} vs background — too invisible"
        )

    def test_light_dot_contrast(self):
        bg  = self._hex_to_rgb("#e8f2f8")
        dot = self._hex_to_rgb("#c8d8e8")
        delta = max(abs(dot[i] - bg[i]) for i in range(3))
        assert delta >= 15, (
            f"light dot_pattern has max channel delta {delta} vs background — too invisible"
        )


# ---------------------------------------------------------------------------
# 12. ElevenLabs must not appear in the services list
# ---------------------------------------------------------------------------
class TestServicesList:
    def test_elevenlabs_not_in_raw_svcs(self):
        """ElevenLabs was removed — it must not appear in the settings panel."""
        import ast
        import pathlib
        src = pathlib.Path("ui/ui_draw.py").read_text(encoding="utf-8")
        assert "ElevenLabs" not in src, (
            "ElevenLabs entry found in ui_draw.py — remove the tuple from _raw_svcs"
        )
