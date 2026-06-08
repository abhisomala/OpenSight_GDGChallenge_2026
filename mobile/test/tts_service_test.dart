// Tests for the TTS completion fallback (EVALUATION.md §2): speak() must always
// resolve within a bounded time even when the underlying engine never reports
// completion, so the controller cannot wedge in `speaking`.

import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/tts_service.dart';

void main() {
  // FlutterTts()'s constructor calls setMethodCallHandler, which needs the test
  // binding's binary messenger. The injected primitives mean no real platform
  // calls are made beyond that.
  TestWidgetsFlutterBinding.ensureInitialized();

  group('FlutterTtsService.speak completion fallback', () {
    test('resolves via the fallback when the engine never reports completion',
        () async {
      var stops = 0;
      final FlutterTtsService service = FlutterTtsService(
        // Never completes — models a missing `awaitSpeakCompletion` callback.
        speakPrimitive: (_) => Completer<void>().future,
        stopPrimitive: () async => stops++,
        fallbackTimeout: (_) => const Duration(milliseconds: 50),
      );

      // The outer guard fails the test if the fallback did not fire; a real hang
      // would blow past it rather than completing.
      await service.speak('some answer text').timeout(const Duration(seconds: 2));

      // Fallback stopped lingering playback (once on entry, once on timeout).
      expect(stops, 2);
    });

    test('empty text is a no-op (no fallback wait)', () async {
      var spoke = false;
      final FlutterTtsService service = FlutterTtsService(
        speakPrimitive: (_) async => spoke = true,
        stopPrimitive: () async {},
        fallbackTimeout: (_) => const Duration(milliseconds: 50),
      );

      await service.speak('   ');

      expect(spoke, isFalse);
    });
  });

  group('speakFallbackTimeout bounds', () {
    test('is hard-capped at maxSpeakTimeout for very long text', () {
      expect(speakFallbackTimeout('x' * 100000), maxSpeakTimeout);
    });

    test('has a floor for short text', () {
      expect(speakFallbackTimeout(''), const Duration(milliseconds: 5000));
    });
  });
}
