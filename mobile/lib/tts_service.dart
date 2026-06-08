/// Text-to-speech seam for the voice client (Phase 4).
///
/// [TtsService] is a thin interface so [VoiceController] can be unit-tested with
/// a fake (no real audio). [FlutterTtsService] is the production implementation
/// backed by the `flutter_tts` plugin, configured so that [speak] resolves only
/// when playback actually finishes — that completion drives `speaking → idle`.
///
/// Note: the app calls this only when a screen reader is NOT active; when
/// TalkBack/VoiceOver is on, the app defers to it and never calls [speak], so
/// the two voices never talk over each other (see [VoiceController]).
library;

import 'dart:async';

import 'package:flutter_tts/flutter_tts.dart';

/// Hard upper bound on how long [FlutterTtsService.speak] will wait for the
/// engine's completion callback before resolving anyway. flutter_tts's
/// `awaitSpeakCompletion` callback is known to occasionally never fire on some
/// Android engines; without this bound the caller would wedge in its "speaking"
/// state forever (EVALUATION.md §2).
const Duration maxSpeakTimeout = Duration(seconds: 30);

/// Fallback wait for one [FlutterTtsService.speak], scaled by [text] length so
/// long answers are not cut off prematurely, with a 5s floor and the
/// [maxSpeakTimeout] hard cap so the wait is always bounded.
Duration speakFallbackTimeout(String text) => Duration(
      milliseconds:
          (text.length * 120).clamp(5000, maxSpeakTimeout.inMilliseconds).toInt(),
    );

/// Abstraction over a text-to-speech engine.
abstract class TtsService {
  /// Speak [text]; the returned future completes when playback finishes.
  Future<void> speak(String text);

  /// Stop any in-progress playback.
  Future<void> stop();

  /// Release native resources.
  Future<void> dispose();
}

/// Production [TtsService] backed by `flutter_tts`.
class FlutterTtsService implements TtsService {
  /// The optional [speakPrimitive] / [stopPrimitive] / [fallbackTimeout] are
  /// seams for testing the completion-fallback without the platform channel; in
  /// production all three are null and the real `flutter_tts` engine is used.
  FlutterTtsService({
    Future<void> Function(String text)? speakPrimitive,
    Future<void> Function()? stopPrimitive,
    Duration Function(String text)? fallbackTimeout,
  })  :
        // ignore: prefer_initializing_formals — public param, private field.
        _speakPrimitive = speakPrimitive,
        // ignore: prefer_initializing_formals — public param, private field.
        _stopPrimitive = stopPrimitive,
        _fallbackTimeout = fallbackTimeout ?? speakFallbackTimeout;

  final FlutterTts _tts = FlutterTts();
  final Future<void> Function(String text)? _speakPrimitive;
  final Future<void> Function()? _stopPrimitive;
  final Duration Function(String text) _fallbackTimeout;
  bool _configured = false;

  Future<void> _ensureConfigured() async {
    if (_configured) return;
    // Make `speak` await actual completion so the caller knows when the answer
    // has finished playing.
    await _tts.awaitSpeakCompletion(true);
    _configured = true;
  }

  Future<void> _rawSpeak(String text) async {
    final Future<void> Function(String text)? override = _speakPrimitive;
    if (override != null) {
      await override(text);
    } else {
      await _tts.speak(text);
    }
  }

  Future<void> _rawStop() async {
    final Future<void> Function()? override = _stopPrimitive;
    if (override != null) {
      await override();
    } else {
      await _tts.stop();
    }
  }

  @override
  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;
    if (_speakPrimitive == null) await _ensureConfigured();
    await _rawStop();
    try {
      // Completion gates the caller's `speaking → idle` transition; bound the
      // wait so a missing completion callback cannot wedge it there forever.
      await _rawSpeak(text).timeout(_fallbackTimeout(text));
    } on TimeoutException {
      // Resolve (don't rethrow): callers await `speak` without a guard, so a
      // throw here would skip their return-to-idle. Stop any lingering playback.
      await _rawStop();
    }
  }

  @override
  Future<void> stop() async {
    await _rawStop();
  }

  @override
  Future<void> dispose() async {
    await _rawStop();
  }
}
