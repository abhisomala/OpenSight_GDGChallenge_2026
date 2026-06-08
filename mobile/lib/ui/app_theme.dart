/// Shared visual language for the OpenSight UI redesign.
///
/// Phase 1 (the Chat / voice screen) defines these tokens; Phases 2–3 (the
/// Agents and Settings tabs) reuse them. This is VIEW-layer only — nothing here
/// touches the [VoiceController] state machine or the engine / STT / TTS
/// services.
///
/// Color values approximate the Figma palette-by-role (see
/// `opensight_ui_spec.md`). The processing/thinking palette (amber→orange,
/// green/cyan/gray step states) is confirmed by the Phase 1 prompt.
library;

import 'package:flutter/material.dart';

/// Dark-theme color tokens, grouped by the role each color plays in the design.
abstract final class AppColors {
  // Surfaces.
  static const Color bgBase = Color(0xFF0A0E17); // near-black navy base
  static const Color surface = Color(0xFF141A28); // cards / panels
  static const Color border = Color(0xFF232A3B); // 1px surface border

  // Accent + text.
  static const Color cyan = Color(0xFF22D3EE); // primary accent
  static const Color textPrimary = Color(0xFFE8EDF4); // near-white
  static const Color textDim = Color(0xFF8A93A6); // captions / "waiting"
  static const Color toggleOff = Color(0xFF3A4150);

  // High-contrast text variants (used when settings.highContrastText is ON):
  // pure white for primary, a much brighter gray for secondary.
  static const Color textPrimaryHigh = Color(0xFFFFFFFF);
  static const Color textDimHigh = Color(0xFFCED6E2);

  // Mic button gradient (idle / listening): blue → purple.
  static const Color micGradStart = Color(0xFF3B82F6);
  static const Color micGradEnd = Color(0xFF8B5CF6);

  // Processing (thinking) palette: amber → orange gradient + amber label.
  static const Color amber = Color(0xFFF59E0B);
  static const Color orange = Color(0xFFF97316);

  // Reasoning-step status colors.
  static const Color stepDone = Color(0xFF22C55E); // green check
  static const Color stepActive = cyan; // cyan spinner
  static const Color stepWaiting = textDim; // gray hollow circle

  // Error accent (absent from Figma — defined here as amber/red, consistent
  // with the controller's recoverable error state).
  static const Color error = Color(0xFFEF4444);
}

/// Corner radius shared by cards, pills, and buttons (~16px per spec).
const double kRadius = 16;

/// Monospace family. Uses the platform's built-in monospace font — on Android
/// `'monospace'` maps to the system mono face — so NO pub dependency and NO
/// bundled font asset are added. The fallback list keeps text sane on other
/// hosts (e.g. the test runner), where it degrades silently to a default font.
const String kMonoFamily = 'monospace';
const List<String> kMonoFallback = <String>['monospace', 'Courier New', 'Courier'];

/// Text styles. The brand title is a bold sans; everything else is monospace —
/// uppercase letter-spaced cyan section headers, and mono body / captions. This
/// mono treatment is core to the look.
abstract final class AppText {
  /// Brand title "OpenSight" — bold sans (platform default sans family).
  static const TextStyle brandTitle = TextStyle(
    color: AppColors.textPrimary,
    fontSize: 20,
    fontWeight: FontWeight.bold,
  );

  /// Cyan tagline under the brand title (mono).
  static const TextStyle tagline = TextStyle(
    color: AppColors.cyan,
    fontFamily: kMonoFamily,
    fontFamilyFallback: kMonoFallback,
    fontSize: 11,
    letterSpacing: 0.5,
  );

  /// Uppercase, letter-spaced cyan mono section header (~12px).
  static const TextStyle sectionHeader = TextStyle(
    color: AppColors.cyan,
    fontFamily: kMonoFamily,
    fontFamilyFallback: kMonoFallback,
    fontSize: 12,
    letterSpacing: 1.5,
    fontWeight: FontWeight.w600,
  );

  /// Mono body / labels (~14px).
  static const TextStyle body = TextStyle(
    color: AppColors.textPrimary,
    fontFamily: kMonoFamily,
    fontFamilyFallback: kMonoFallback,
    fontSize: 14,
  );

  /// Dim mono caption (~13px) — descriptions, "Waiting for request", etc.
  static const TextStyle caption = TextStyle(
    color: AppColors.textDim,
    fontFamily: kMonoFamily,
    fontFamilyFallback: kMonoFallback,
    fontSize: 13,
  );

  /// Effective body style, honoring the high-contrast setting: when [highContrast]
  /// is on, swap to a pure-white color and a heavier weight so the text reads at
  /// maximum brightness. Screens call this instead of [body] directly.
  static TextStyle bodyFor(bool highContrast) => highContrast
      ? body.copyWith(
          color: AppColors.textPrimaryHigh, fontWeight: FontWeight.w600)
      : body;

  /// Effective caption style, honoring the high-contrast setting: a much brighter
  /// secondary color when on.
  static TextStyle captionFor(bool highContrast) =>
      highContrast ? caption.copyWith(color: AppColors.textDimHigh) : caption;
}

/// The five OpenSight agents. Each has its own accent color (Figma palette).
enum AgentKind { brain, shopping, calendar, research, general }

/// Static presentation data for an [AgentKind]: display name, sub-label, accent
/// color, and icon. Used by [AgentBanner] now and by the Agents tab in Phase 2.
class AgentInfo {
  const AgentInfo(this.name, this.subLabel, this.color, this.icon);

  final String name;
  final String subLabel;
  final Color color;
  final IconData icon;

  static const Map<AgentKind, AgentInfo> _all = <AgentKind, AgentInfo>{
    AgentKind.brain:
        AgentInfo('BRAIN', 'routing requests', Color(0xFF3B82F6), Icons.psychology),
    AgentKind.shopping:
        AgentInfo('SHOPPING', 'scanning options', Color(0xFF22C55E), Icons.shopping_bag),
    AgentKind.calendar:
        AgentInfo('CALENDAR', 'checking schedules', Color(0xFFF59E0B), Icons.calendar_today),
    AgentKind.research:
        AgentInfo('RESEARCH', 'pulling sources', Color(0xFFA855F7), Icons.science),
    AgentKind.general:
        AgentInfo('GENERAL', 'composing responses', Color(0xFFF97316), Icons.auto_awesome),
  };

  /// Presentation data for [kind].
  static AgentInfo of(AgentKind kind) => _all[kind]!;
}
