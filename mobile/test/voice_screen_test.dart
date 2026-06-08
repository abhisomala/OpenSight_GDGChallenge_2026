// Widget tests for VoiceScreen (Phase 4): the Semantics label updates per state
// across the real record → query → speak flow, and the whole screen is one tap
// target. Speech/TTS are gated fakes so each state can be observed.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/speech_service.dart';
import 'package:voice_client/tts_service.dart';
import 'package:voice_client/voice_controller.dart';
import 'package:voice_client/voice_screen.dart';

/// Mic whose result is delivered when [heard] completes (holds `listening`).
class GatedSpeech implements SpeechService {
  final Completer<String> heard = Completer<String>();
  @override
  Future<bool> initialize() async => true;
  @override
  Future<String> listenOnce() => heard.future;
  @override
  Future<void> dispose() async {}
}

/// TTS that finishes when [done] completes (holds `speaking`).
class GatedTts implements TtsService {
  final Completer<void> done = Completer<void>();
  final List<String> spoken = <String>[];
  @override
  Future<void> speak(String text) {
    spoken.add(text);
    return done.future;
  }

  @override
  Future<void> stop() async {}
  @override
  Future<void> dispose() async {}
}

/// Mic that reports not-ready (permission denied path).
class DeniedSpeech implements SpeechService {
  @override
  Future<bool> initialize() async => false;
  @override
  Future<String> listenOnce() async => '';
  @override
  Future<void> dispose() async {}
}

class ImmediateTts implements TtsService {
  final List<String> spoken = <String>[];
  @override
  Future<void> speak(String text) async => spoken.add(text);
  @override
  Future<void> stop() async {}
  @override
  Future<void> dispose() async {}
}

void main() {
  testWidgets('Semantics label updates across idle → listening → thinking → '
      'speaking → idle', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();

    final GatedSpeech speech = GatedSpeech();
    final GatedTts tts = GatedTts();
    final Completer<String> engine = Completer<String>();
    final controller = VoiceController(
      speech: speech,
      tts: tts,
      sendQuery: (String text, {void Function(Map<String, dynamic>)? onWorking}) {
        onWorking?.call(<String, dynamic>{'type': 'status'});
        return engine.future;
      },
      screenReaderActive: () => false,
    );

    await tester.pumpWidget(MaterialApp(home: VoiceScreen(controller: controller)));

    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.idle)),
        findsOneWidget);

    // Tap → listening (mic result still pending).
    await tester.tap(find.byType(VoiceScreen));
    await tester.pump();
    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.listening)),
        findsOneWidget);

    // Deliver the final transcript → thinking (engine response still pending).
    speech.heard.complete('find headphones');
    await tester.pump();
    await tester.pump();
    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.thinking)),
        findsOneWidget);

    // Engine answers → speaking; the label carries the answer text.
    engine.complete('Found some headphones.');
    await tester.pump();
    await tester.pump();
    expect(
      find.bySemanticsLabel(
          voiceSemanticLabel(VoiceState.speaking, answer: 'Found some headphones.')),
      findsOneWidget,
    );
    expect(find.text('Found some headphones.'), findsOneWidget);
    expect(tts.spoken, <String>['Found some headphones.']);

    // TTS finishes → idle.
    tts.done.complete();
    await tester.pump();
    await tester.pump();
    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.idle)),
        findsOneWidget);

    handle.dispose();
  });

  testWidgets('permission-denied error is announced and a tap returns to idle',
      (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final controller = VoiceController(
      speech: DeniedSpeech(),
      tts: ImmediateTts(),
      sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
      screenReaderActive: () => false,
    );

    await tester.pumpWidget(MaterialApp(home: VoiceScreen(controller: controller)));

    await tester.tap(find.byType(VoiceScreen));
    await tester.pumpAndSettle();
    expect(
      find.bySemanticsLabel(voiceSemanticLabel(VoiceState.error,
          error: 'Microphone permission is needed.')),
      findsOneWidget,
    );

    await tester.tap(find.byType(VoiceScreen)); // tap from error → idle
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.idle)),
        findsOneWidget);

    handle.dispose();
  });

  testWidgets('mic is the primary semantic button (smaller than the screen) '
      'and tapping anywhere still routes to handleTap',
      (WidgetTester tester) async {
    // The redesign retired the single full-screen-button model in favor of a
    // conversation/log + a primary mic button. The per-state label now rides on
    // the mic button (a node smaller than the screen), and a full-screen
    // GestureDetector preserves the eyes-free "tap anywhere" affordance.
    final SemanticsHandle handle = tester.ensureSemantics();
    final controller = VoiceController(
      speech: GatedSpeech(),
      tts: ImmediateTts(),
      sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'ok',
      screenReaderActive: () => false,
    );

    await tester.pumpWidget(MaterialApp(home: VoiceScreen(controller: controller)));

    final Finder button =
        find.bySemanticsLabel(voiceSemanticLabel(VoiceState.idle));
    expect(button, findsOneWidget);

    final Size screen = tester.getSize(find.byType(VoiceScreen));
    final Rect rect = tester.getRect(button);
    expect(rect.width, lessThan(screen.width));
    expect(rect.height, lessThan(screen.height));

    // A tap anywhere on the screen still drives the controller (idle → listening).
    await tester.tap(find.byType(VoiceScreen));
    await tester.pump();
    expect(controller.state, VoiceState.listening);

    handle.dispose();
  });
}
