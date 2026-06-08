// Widget tests for the redesigned Chat voice screen (conversation refinement).
//
// These assert: the restyled screen exposes the correct per-state label on the
// MIC button (the primary semantic button); a completed turn renders YOU /
// OPENSIGHT conversation bubbles; the ReasoningFlow counter + per-step states
// track the progression (active marker advances); the DONE indicator is the
// muted/outlined glyph (not the bright filled one); the reasoning steps are an
// ordered list for screen readers; and the screen builds/settles under
// MediaQuery.disableAnimations.
//
// Animated states are driven with reduce-motion ON so no controller keeps
// ticking and pumpAndSettle is safe; voice_screen_test.dart covers motion-on.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/speech_service.dart';
import 'package:voice_client/tts_service.dart';
import 'package:voice_client/ui/reasoning_flow.dart';
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
  @override
  Future<void> speak(String text) => done.future;
  @override
  Future<void> stop() async {}
  @override
  Future<void> dispose() async {}
}

/// Mic that reports not-ready (permission-denied → error path).
class DeniedSpeech implements SpeechService {
  @override
  Future<bool> initialize() async => false;
  @override
  Future<String> listenOnce() async => '';
  @override
  Future<void> dispose() async {}
}

class ImmediateTts implements TtsService {
  @override
  Future<void> speak(String text) async {}
  @override
  Future<void> stop() async {}
  @override
  Future<void> dispose() async {}
}

/// Wrap [screen] so the closest MediaQuery to it forces [disableAnimations].
Widget _host(Widget screen, {bool disableAnimations = true}) {
  return MaterialApp(
    home: Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context)
            .copyWith(disableAnimations: disableAnimations),
        child: screen,
      ),
    ),
  );
}

/// Drive [controller] from idle into `thinking` (query sent, engine pending).
Future<void> _toThinking(
  WidgetTester tester,
  GatedSpeech speech,
  Completer<String> engine,
) async {
  await tester.tap(find.byType(VoiceScreen));
  await tester.pump();
  speech.heard.complete('find headphones');
  await tester.pump();
  await tester.pump();
}

void main() {
  group('per-state semantic label (mic button) + chrome, reduce-motion ON', () {
    testWidgets('idle shows prompt + caption, no bubbles',
        (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final controller = VoiceController(
        speech: GatedSpeech(),
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );

      await tester.pumpWidget(_host(VoiceScreen(controller: controller)));

      expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.idle)),
          findsOneWidget);
      // The header (logo + "OpenSight" + tagline) now lives on the nav shell,
      // not the Chat tab — see home_shell_test.dart. The Chat tab still owns its
      // own idle prompt + caption.
      expect(find.text('Gemini · Deepgram · Google TTS'), findsOneWidget);
      expect(find.text('Tap the microphone below and speak your request.'),
          findsOneWidget);
      // No conversation yet.
      expect(find.text('YOU'), findsNothing);
      expect(find.text('OPENSIGHT'), findsNothing);

      handle.dispose();
    });

    testWidgets('listening', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final controller = VoiceController(
        speech: GatedSpeech(), // listenOnce never completes → holds listening
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );

      await tester.pumpWidget(_host(VoiceScreen(controller: controller)));
      await tester.tap(find.byType(VoiceScreen));
      await tester.pump();

      expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.listening)),
          findsOneWidget);

      handle.dispose();
    });

    testWidgets('thinking: YOU bubble + AgentBanner + ReasoningFlow + ordered '
        'step semantics', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final GatedSpeech speech = GatedSpeech();
      final Completer<String> engine = Completer<String>();
      final controller = VoiceController(
        speech: speech,
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) {
          onWorking?.call(<String, dynamic>{'type': 'status'});
          return engine.future; // never completes → holds thinking
        },
        screenReaderActive: () => false,
      );

      await tester.pumpWidget(_host(VoiceScreen(controller: controller)));
      await _toThinking(tester, speech, engine);

      expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.thinking)),
          findsOneWidget);
      // The user's query is shown as a YOU bubble + announced as a live region.
      expect(find.text('YOU'), findsOneWidget);
      expect(find.text('find headphones'), findsOneWidget);
      expect(find.bySemanticsLabel('You said: find headphones'), findsOneWidget);
      // Default agent banner + reasoning panel.
      expect(find.text('BRAIN'), findsOneWidget);
      expect(find.text('REASONING FLOW'), findsOneWidget);
      expect(find.text('2 / 5'), findsOneWidget); // frozen mid-flow frame
      // Steps are an ordered list for screen readers.
      expect(find.bySemanticsLabel(RegExp(r'Step 1 of 5')), findsOneWidget);
      expect(find.bySemanticsLabel(RegExp(r'Step 5 of 5')), findsOneWidget);

      handle.dispose();
    });

    testWidgets('speaking: YOU + OPENSIGHT bubbles + complete ReasoningFlow',
        (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final GatedSpeech speech = GatedSpeech();
      final GatedTts tts = GatedTts(); // speak never completes → holds speaking
      final Completer<String> engine = Completer<String>();
      final controller = VoiceController(
        speech: speech,
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) =>
            engine.future,
        screenReaderActive: () => false,
      );

      await tester.pumpWidget(_host(VoiceScreen(controller: controller)));
      await tester.tap(find.byType(VoiceScreen));
      await tester.pump();
      speech.heard.complete('find headphones');
      await tester.pump();
      engine.complete('Found some headphones.');
      await tester.pump();
      await tester.pump();

      expect(
        find.bySemanticsLabel(voiceSemanticLabel(VoiceState.speaking,
            answer: 'Found some headphones.')),
        findsOneWidget,
      );
      // Both bubbles present with their text.
      expect(find.text('YOU'), findsOneWidget);
      expect(find.text('find headphones'), findsOneWidget);
      expect(find.text('OPENSIGHT'), findsOneWidget);
      expect(find.text('Found some headphones.'), findsOneWidget);
      expect(find.bySemanticsLabel('OpenSight said: Found some headphones.'),
          findsOneWidget);
      expect(find.text('5 / 5'), findsOneWidget);

      handle.dispose();
    });

    testWidgets('error', (WidgetTester tester) async {
      final SemanticsHandle handle = tester.ensureSemantics();
      final controller = VoiceController(
        speech: DeniedSpeech(),
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );

      await tester.pumpWidget(_host(VoiceScreen(controller: controller)));
      await tester.tap(find.byType(VoiceScreen));
      await tester.pumpAndSettle();

      expect(
        find.bySemanticsLabel(voiceSemanticLabel(VoiceState.error,
            error: 'Microphone permission is needed.')),
        findsOneWidget,
      );

      handle.dispose();
    });
  });

  group('ReasoningFlow counter + per-step states (active marker advances)', () {
    Future<void> pumpFlow(WidgetTester tester, int completed,
        {bool showActive = true}) {
      return tester.pumpWidget(_host(
        Scaffold(
          body: ReasoningFlow(
            completedSteps: completed,
            showActive: showActive,
            reduceMotion: true,
          ),
        ),
      ));
    }

    testWidgets('0 done → 0/5, first step active, four waiting',
        (WidgetTester tester) async {
      await pumpFlow(tester, 0);
      expect(find.text('0 / 5'), findsOneWidget);
      expect(find.text('done'), findsNothing);
      expect(find.text('active'), findsOneWidget);
      expect(find.text('waiting'), findsNWidgets(4));
    });

    testWidgets('3 done → 3/5, active advanced, one waiting',
        (WidgetTester tester) async {
      await pumpFlow(tester, 3);
      expect(find.text('3 / 5'), findsOneWidget);
      expect(find.text('done'), findsNWidgets(3));
      expect(find.text('active'), findsOneWidget);
      expect(find.text('waiting'), findsOneWidget);
    });

    testWidgets('complete (5/5, no active) → five done, none active/waiting',
        (WidgetTester tester) async {
      await pumpFlow(tester, 5, showActive: false);
      expect(find.text('5 / 5'), findsOneWidget);
      expect(find.text('done'), findsNWidgets(5));
      expect(find.text('active'), findsNothing);
      expect(find.text('waiting'), findsNothing);
    });
  });

  testWidgets('DONE indicator is muted/outlined (not bright filled)',
      (WidgetTester tester) async {
    await tester.pumpWidget(_host(
      const Scaffold(
        body: ReasoningFlow(completedSteps: 3, reduceMotion: true),
      ),
    ));
    expect(find.byIcon(Icons.check_circle_outline), findsNWidgets(3));
    expect(find.byIcon(Icons.check_circle), findsNothing);
  });

  testWidgets('reasoning steps expose ordered-list semantics',
      (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    await tester.pumpWidget(_host(
      const Scaffold(
        body: ReasoningFlow(completedSteps: 2, reduceMotion: true),
      ),
    ));
    expect(find.bySemanticsLabel('Step 1 of 5: Classify intent, done'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Step 3 of 5: Route to agent, active'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Step 5 of 5: Generate response, waiting'),
        findsOneWidget);
    handle.dispose();
  });

  testWidgets('screen sweeps all states under reduce-motion without error',
      (WidgetTester tester) async {
    final GatedSpeech speech = GatedSpeech();
    final controller = VoiceController(
      speech: speech,
      tts: ImmediateTts(),
      sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
        onWorking?.call(<String, dynamic>{'type': 'status'});
        return 'done';
      },
      screenReaderActive: () => false,
    );

    await tester.pumpWidget(_host(VoiceScreen(controller: controller)));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    // Tap → listening; complete STT → listening → thinking → speaking → idle.
    await tester.tap(find.byType(VoiceScreen));
    await tester.pump();
    speech.heard.complete('find headphones');
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });
}
