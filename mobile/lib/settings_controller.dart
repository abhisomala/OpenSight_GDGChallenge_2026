/// In-memory settings for the OpenSight client (Phase 3).
///
/// A [ChangeNotifier] holding the user's Model Configuration + Accessibility
/// choices. IN-MEMORY ONLY — there is NO persistence and NO new dependency, so
/// toggles reset to their defaults on restart. That is acceptable for this POC.
///
/// Ownership lives in the nav shell (`home_shell.dart`), which passes this to the
/// Settings screen (to bind the controls), to the [VoiceController] (which reads
/// the accessibility settings to gate three behaviors), and to the screens that
/// resolve high-contrast text.
library;

import 'package:flutter/foundation.dart';

/// The user-tunable settings. Each setter notifies listeners so the UI and the
/// controller react immediately.
class SettingsController extends ChangeNotifier {
  // ---- Model configuration -------------------------------------------------

  String _geminiModel = 'Gemini 2.5 Flash';

  /// The selected language model name. DISPLAY/LOCAL ONLY: the model is chosen
  /// server-side and the `/ws` contract has no model field, so this never alters
  /// the round trip — it only updates local state.
  String get geminiModel => _geminiModel;
  set geminiModel(String value) {
    if (value == _geminiModel) return;
    _geminiModel = value;
    notifyListeners();
  }

  // ---- Accessibility -------------------------------------------------------

  bool _screenReaderMode = false;

  /// Manual screen-reader mode. When ON, the app treats itself as if a screen
  /// reader is present (stays silent, defers to the live region). It may only
  /// FORCE the defer path on — it never forces speech when a real OS reader is
  /// present. (See `VoiceController._effectiveScreenReader`.)
  bool get screenReaderMode => _screenReaderMode;
  set screenReaderMode(bool value) {
    if (value == _screenReaderMode) return;
    _screenReaderMode = value;
    notifyListeners();
  }

  bool _announceAgentChanges = true;

  /// When ON, a newly active specialist agent is announced aloud.
  bool get announceAgentChanges => _announceAgentChanges;
  set announceAgentChanges(bool value) {
    if (value == _announceAgentChanges) return;
    _announceAgentChanges = value;
    notifyListeners();
  }

  bool _hapticFeedback = true;

  /// When ON, [HapticFeedback] fires on state changes (gated in the view).
  bool get hapticFeedback => _hapticFeedback;
  set hapticFeedback(bool value) {
    if (value == _hapticFeedback) return;
    _hapticFeedback = value;
    notifyListeners();
  }

  bool _highContrastText = false;

  /// When ON, body/secondary text resolves to a higher-contrast variant.
  bool get highContrastText => _highContrastText;
  set highContrastText(bool value) {
    if (value == _highContrastText) return;
    _highContrastText = value;
    notifyListeners();
  }
}
