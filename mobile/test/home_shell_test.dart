// Widget tests for the Phase 2 navigation shell + Agents screen.
//
// Cover: the nav renders three tabs (with per-tab selected/button semantics);
// switching tabs preserves Chat state (the injected controller is not recreated
// and its state persists across a tab round-trip); the Agents screen renders all
// five agent cards (with name + sub-label semantics) plus the reasoning panel in
// its idle 0/5 reference state with ordered-list step semantics.
//
// Tests run with reduce-motion ON so the listening glow / nav box transitions
// don't keep ticking and pumpAndSettle stays safe.

import 'dart:async';

import 'dart:ui' show Tristate;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/home_shell.dart';
import 'package:voice_client/settings_controller.dart';
import 'package:voice_client/speech_service.dart';
import 'package:voice_client/tts_service.dart';
import 'package:voice_client/voice_controller.dart';
import 'package:voice_client/voice_screen.dart';

/// Mic whose result never arrives → holds `listening` for the state-persistence
/// test.
class GatedSpeech implements SpeechService {
  final Completer<String> heard = Completer<String>();
  @override
  Future<bool> initialize() async => true;
  @override
  Future<String> listenOnce() => heard.future;
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

VoiceController _injectedController() => VoiceController(
      speech: GatedSpeech(),
      tts: ImmediateTts(),
      sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
      screenReaderActive: () => false,
    );

/// Host the shell with reduce-motion forced on (closest MediaQuery to it).
Widget _host(Widget shell) {
  return MaterialApp(
    home: Builder(
      builder: (BuildContext context) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: true),
        child: shell,
      ),
    ),
  );
}

void main() {
  testWidgets('nav renders three tabs with per-tab button/selected semantics',
      (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final VoiceController controller = _injectedController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(_host(HomeShell(controller: controller)));
    await tester.pumpAndSettle();

    expect(find.bySemanticsLabel('Chat tab'), findsOneWidget);
    expect(find.bySemanticsLabel('Agents tab'), findsOneWidget);
    expect(find.bySemanticsLabel('Settings tab'), findsOneWidget);

    // Chat is selected initially; its node is a selected button. Agents is a
    // button but not selected.
    // isButton is a plain bool flag; isSelected is a Tristate (true/false/none).
    final chat = tester.getSemantics(find.bySemanticsLabel('Chat tab'));
    expect(chat.flagsCollection.isButton, isTrue);
    expect(chat.flagsCollection.isSelected, Tristate.isTrue);
    final agents = tester.getSemantics(find.bySemanticsLabel('Agents tab'));
    expect(agents.flagsCollection.isButton, isTrue);
    expect(agents.flagsCollection.isSelected, isNot(Tristate.isTrue));

    handle.dispose();
  });

  testWidgets('switching tabs preserves Chat state (controller not recreated)',
      (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final VoiceController controller = _injectedController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(_host(HomeShell(controller: controller)));
    await tester.pumpAndSettle();

    // Start a query on the Chat tab → listening (mic result is held).
    await tester.tap(find.byType(VoiceScreen));
    await tester.pumpAndSettle();
    expect(controller.state, VoiceState.listening);

    // Switch Chat → Agents → Settings → back to Chat.
    await tester.tap(find.bySemanticsLabel('Agents tab'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Settings tab'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Chat tab'));
    await tester.pumpAndSettle();

    // Same controller instance, state preserved across the round-trip.
    expect(controller.state, VoiceState.listening);
    expect(find.bySemanticsLabel(voiceSemanticLabel(VoiceState.listening)),
        findsOneWidget);

    handle.dispose();
  });

  testWidgets('Agents screen: five cards + reasoning panel + card semantics',
      (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final VoiceController controller = _injectedController();
    addTearDown(controller.dispose);

    await tester.pumpWidget(_host(HomeShell(controller: controller)));
    await tester.pumpAndSettle();

    await tester.tap(find.bySemanticsLabel('Agents tab'));
    await tester.pumpAndSettle();

    // Section header + footer.
    expect(find.text('BRAIN / AGENTS'), findsOneWidget);
    expect(find.text('OpenSight v1.0'), findsOneWidget);

    // All five agent names render (visible text).
    for (final String name in <String>[
      'BRAIN',
      'SHOPPING',
      'CALENDAR',
      'RESEARCH',
      'GENERAL',
    ]) {
      expect(find.text(name), findsOneWidget);
    }

    // Per-card semantics: each is a labeled button (name + sub-label).
    expect(find.bySemanticsLabel('BRAIN, routing requests'), findsOneWidget);
    expect(find.bySemanticsLabel('SHOPPING, scanning options'), findsOneWidget);
    expect(find.bySemanticsLabel('CALENDAR, checking schedules'), findsOneWidget);
    expect(find.bySemanticsLabel('RESEARCH, pulling sources'), findsOneWidget);
    expect(
        find.bySemanticsLabel('GENERAL, composing responses'), findsOneWidget);

    // Reasoning panel in its idle reference state: 0/5, all waiting, with the
    // Phase-1 ordered-list step semantics intact.
    expect(find.text('REASONING FLOW'), findsOneWidget);
    expect(find.text('0 / 5'), findsOneWidget);
    expect(find.text('waiting'), findsNWidgets(5));
    expect(find.bySemanticsLabel('Step 1 of 5: Classify intent, waiting'),
        findsOneWidget);
    expect(find.bySemanticsLabel('Step 5 of 5: Generate response, waiting'),
        findsOneWidget);

    handle.dispose();
  });

  // ---- Phase 3: Settings tab + wiring --------------------------------------

  testWidgets('Settings toggles are accessible switches; values persist across '
      'tab switches', (WidgetTester tester) async {
    final SemanticsHandle handle = tester.ensureSemantics();
    final SettingsController settings = SettingsController();
    final VoiceController controller = _injectedController();
    addTearDown(controller.dispose);
    addTearDown(settings.dispose);

    await tester.pumpWidget(
        _host(HomeShell(controller: controller, settings: settings)));
    await tester.pumpAndSettle();

    // Open Settings.
    await tester.tap(find.bySemanticsLabel('Settings tab'));
    await tester.pumpAndSettle();

    expect(find.text('MODEL CONFIGURATION'), findsOneWidget);
    expect(find.text('ACCESSIBILITY'), findsOneWidget);
    expect(find.text('ABOUT'), findsOneWidget);
    expect(find.text('Deepgram'), findsOneWidget);
    expect(find.text('Google TTS'), findsOneWidget);

    // The "High contrast text" row is a switch, initially off.
    final Finder hc = find.bySemanticsLabel('High contrast text');
    expect(hc, findsOneWidget);
    expect(tester.getSemantics(hc).flagsCollection.isToggled, Tristate.isFalse);

    // Toggle it on through the UI (tap the row's title, inside the InkWell).
    // Scroll it into view first — it's the last toggle, below the test fold.
    await tester.ensureVisible(find.text('High contrast text'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('High contrast text'));
    await tester.pumpAndSettle();
    expect(settings.highContrastText, isTrue);
    expect(tester.getSemantics(find.bySemanticsLabel('High contrast text'))
        .flagsCollection.isToggled, Tristate.isTrue);

    // Switch away to Chat and back; the value is retained.
    await tester.tap(find.bySemanticsLabel('Chat tab'));
    await tester.pumpAndSettle();
    await tester.tap(find.bySemanticsLabel('Settings tab'));
    await tester.pumpAndSettle();
    expect(settings.highContrastText, isTrue);
    expect(tester.getSemantics(find.bySemanticsLabel('High contrast text'))
        .flagsCollection.isToggled, Tristate.isTrue);

    handle.dispose();
  });

  group('haptic-feedback gate (view)', () {
    /// Count platform HapticFeedback.vibrate calls while [body] runs.
    Future<int> vibrationsDuring(
      WidgetTester tester,
      Future<void> Function() body,
    ) async {
      int vibrations = 0;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (MethodCall call) async {
          if (call.method == 'HapticFeedback.vibrate') vibrations++;
          return null;
        },
      );
      addTearDown(() => tester.binding.defaultBinaryMessenger
          .setMockMethodCallHandler(SystemChannels.platform, null));
      await body();
      return vibrations;
    }

    testWidgets('OFF ⇒ a state change does NOT fire a haptic',
        (WidgetTester tester) async {
      final SettingsController settings = SettingsController()
        ..hapticFeedback = false;
      final GatedSpeech speech = GatedSpeech();
      final VoiceController controller = VoiceController(
        speech: speech,
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
        settings: settings,
      );
      addTearDown(controller.dispose);
      addTearDown(settings.dispose);

      final int vibrations = await vibrationsDuring(tester, () async {
        await tester.pumpWidget(
            _host(HomeShell(controller: controller, settings: settings)));
        await tester.pumpAndSettle();
        // Tap → listening (a state change).
        await tester.tap(find.byType(VoiceScreen));
        await tester.pump();
      });

      expect(controller.state, VoiceState.listening);
      expect(vibrations, 0);
    });

    testWidgets('ON ⇒ a state change fires a haptic',
        (WidgetTester tester) async {
      final SettingsController settings = SettingsController(); // haptics on
      final GatedSpeech speech = GatedSpeech();
      final VoiceController controller = VoiceController(
        speech: speech,
        tts: ImmediateTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
        settings: settings,
      );
      addTearDown(controller.dispose);
      addTearDown(settings.dispose);

      final int vibrations = await vibrationsDuring(tester, () async {
        await tester.pumpWidget(
            _host(HomeShell(controller: controller, settings: settings)));
        await tester.pumpAndSettle();
        await tester.tap(find.byType(VoiceScreen));
        await tester.pump();
      });

      expect(controller.state, VoiceState.listening);
      expect(vibrations, greaterThan(0));
    });
  });
}
