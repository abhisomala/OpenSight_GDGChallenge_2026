/// Speech-to-text seam for the voice client (Phase 4).
///
/// [SpeechService] is a thin interface so [VoiceController] can be unit-tested
/// with a fake (no real microphone). [SttSpeechService] is the production
/// implementation backed by the `speech_to_text` plugin. Per the spec, only the
/// FINAL recognition result is used — partial results are ignored so that one
/// tap produces exactly one query.
library;

import 'dart:async';

import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_recognition_result.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// Raised for any speech problem (no permission, no speech, timeout, or a
/// recognition error). The controller maps these to the recoverable error
/// state. [permissionDenied] distinguishes the mic-permission case so the
/// spoken/announced message can be specific.
class SpeechException implements Exception {
  SpeechException(this.message, {this.permissionDenied = false});

  final String message;
  final bool permissionDenied;

  @override
  String toString() => 'SpeechException: $message';
}

/// Abstraction over a single-utterance speech recognizer.
abstract class SpeechService {
  /// Initialize the engine and ensure microphone permission (requested on first
  /// use). Returns `true` when ready to listen, `false` if unavailable / denied.
  Future<bool> initialize();

  /// Listen for one utterance and resolve with the FINAL recognized text.
  /// Throws [SpeechException] on timeout or a recognition error. May resolve
  /// with an empty string if nothing intelligible was heard.
  Future<String> listenOnce();

  /// Release native resources.
  Future<void> dispose();
}

/// Production [SpeechService] backed by `speech_to_text`.
class SttSpeechService implements SpeechService {
  SttSpeechService({
    this.listenFor = const Duration(seconds: 30),
    this.pauseFor = const Duration(seconds: 3),
  });

  /// Hard cap on how long a single utterance may run.
  final Duration listenFor;

  /// Silence after speech that ends the utterance.
  final Duration pauseFor;

  final SpeechToText _stt = SpeechToText();
  Completer<String>? _active;

  @override
  Future<bool> initialize() {
    return _stt.initialize(
      onError: _onError,
      onStatus: _onStatus,
    );
  }

  void _onError(SpeechRecognitionError error) {
    final Completer<String>? c = _active;
    if (c != null && !c.isCompleted) {
      c.completeError(SpeechException(error.errorMsg));
    }
  }

  void _onStatus(String status) {
    // When the engine stops with no final result, resolve empty so the
    // controller can treat it as "didn't catch that".
    if (status == 'done' || status == 'notListening') {
      final Completer<String>? c = _active;
      if (c != null && !c.isCompleted) c.complete('');
    }
  }

  @override
  Future<String> listenOnce() async {
    final Completer<String> c = Completer<String>();
    _active = c;

    await _stt.listen(
      onResult: (SpeechRecognitionResult result) {
        if (result.finalResult && !c.isCompleted) {
          c.complete(result.recognizedWords);
        }
      },
      // Final result only — no partials (one tap → one query).
      listenOptions: SpeechListenOptions(
        partialResults: false,
        listenFor: listenFor,
        pauseFor: pauseFor,
      ),
    );

    try {
      return await c.future.timeout(
        listenFor + const Duration(seconds: 5),
        onTimeout: () => throw SpeechException('Listening timed out'),
      );
    } finally {
      _active = null;
      await _stt.stop();
    }
  }

  @override
  Future<void> dispose() async {
    await _stt.cancel();
  }
}
