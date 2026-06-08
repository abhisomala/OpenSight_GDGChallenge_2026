// State-machine tests for VoiceController (Phase 4): record → query → speak,
// permission/STT/engine error mapping, the mock-query fallback, and the
// screen-reader serialization (flutter_tts is NOT used when a reader is active).

import 'package:flutter_test/flutter_test.dart';
import 'package:voice_client/engine_client.dart';
import 'package:voice_client/settings_controller.dart';
import 'package:voice_client/speech_service.dart';
import 'package:voice_client/tts_service.dart';
import 'package:voice_client/voice_controller.dart';
import 'package:voice_client/voice_screen.dart';

/// Fake mic: returns [result] as the final transcript, or throws [error], or
/// reports not-ready via [ready].
class FakeSpeech implements SpeechService {
  FakeSpeech({this.ready = true, this.result = 'wireless headphones', this.error});

  bool ready;
  String result;
  SpeechException? error;
  int initializeCalls = 0;
  int listenCalls = 0;

  @override
  Future<bool> initialize() async {
    initializeCalls++;
    return ready;
  }

  @override
  Future<String> listenOnce() async {
    listenCalls++;
    if (error != null) throw error!;
    return result;
  }

  @override
  Future<void> dispose() async {}
}

/// Fake TTS: records everything it was asked to speak.
class FakeTts implements TtsService {
  final List<String> spoken = <String>[];

  @override
  Future<void> speak(String text) async => spoken.add(text);

  @override
  Future<void> stop() async {}

  @override
  Future<void> dispose() async {}
}

void main() {
  group('happy path (real mic, no screen reader)', () {
    test('idle → listening → thinking → speaking → idle; query + answer spoken',
        () async {
      final speech = FakeSpeech(result: 'find me headphones');
      final tts = FakeTts();
      String? sent;
      final controller = VoiceController(
        speech: speech,
        tts: tts,
        sendQuery: (String text, {void Function(Map<String, dynamic>)? onWorking}) async {
          sent = text;
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'BRAIN'});
          return 'Here are some headphones.';
        },
        screenReaderActive: () => false,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq, <VoiceState>[
        VoiceState.listening,
        VoiceState.thinking,
        VoiceState.speaking,
        VoiceState.idle,
      ]);
      expect(sent, 'find me headphones'); // final STT result is the query
      expect(controller.responseText, 'Here are some headphones.');
      expect(tts.spoken, <String>['Here are some headphones.']); // answer spoken
    });
  });

  group('error mapping (all recoverable)', () {
    test('permission denied → error, audible message, tap → idle', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(ready: false),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq, <VoiceState>[VoiceState.listening, VoiceState.error]);
      expect(controller.errorMessage, contains('Microphone permission'));
      expect(tts.spoken.single, contains('Microphone permission'));

      await controller.handleTap(); // tap from error
      expect(seq.last, VoiceState.idle);
    });

    test('STT recognition error → error', () async {
      final controller = VoiceController(
        speech: FakeSpeech(error: SpeechException('no match')),
        tts: FakeTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq, <VoiceState>[VoiceState.listening, VoiceState.error]);
      expect(controller.errorMessage, contains("didn't catch"));
    });

    test('no speech (empty final result) → error', () async {
      final controller = VoiceController(
        speech: FakeSpeech(result: '   '),
        tts: FakeTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => false,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq, <VoiceState>[VoiceState.listening, VoiceState.error]);
      expect(controller.errorMessage, contains("didn't catch"));
    });

    test('engine transport failure → error', () async {
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hello'),
        tts: FakeTts(),
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
          throw EngineConnectionException('boom');
        },
        screenReaderActive: () => false,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq, <VoiceState>[
        VoiceState.listening,
        VoiceState.thinking,
        VoiceState.error,
      ]);
      expect(controller.errorMessage, contains('reach the server'));
    });
  });

  group('mock-query fallback', () {
    test('skips the mic and sends the preset query', () async {
      final speech = FakeSpeech();
      String? sent;
      final controller = VoiceController(
        speech: speech,
        tts: FakeTts(),
        sendQuery: (String text, {void Function(Map<String, dynamic>)? onWorking}) async {
          sent = text;
          return 'answer';
        },
        screenReaderActive: () => false,
        useMockQuery: true,
        mockQuery: 'preset query',
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(speech.initializeCalls, 0); // mic never opened
      expect(speech.listenCalls, 0);
      expect(sent, 'preset query');
      expect(seq, <VoiceState>[
        VoiceState.listening,
        VoiceState.thinking,
        VoiceState.speaking,
        VoiceState.idle,
      ]);
    });
  });

  group('screen-reader serialization', () {
    test('does NOT call flutter_tts when a screen reader is active', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'The answer.',
        screenReaderActive: () => true,
        estimateReadTime: (_) => Duration.zero,
      );
      final List<VoiceState> seq = <VoiceState>[];
      controller.addListener(() => seq.add(controller.state));

      await controller.handleTap();

      expect(seq.last, VoiceState.idle);
      expect(seq, contains(VoiceState.speaking));
      expect(tts.spoken, isEmpty); // deferred to the screen reader
    });

    test('error is not spoken by flutter_tts under a screen reader', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(ready: false),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'x',
        screenReaderActive: () => true,
        estimateReadTime: (_) => Duration.zero,
      );

      await controller.handleTap();

      expect(tts.spoken, isEmpty);
      expect(controller.errorMessage, contains('Microphone permission'));
    });
  });

  test('taps while busy are ignored (no overlapping query)', () async {
    var calls = 0;
    final controller = VoiceController(
      speech: FakeSpeech(),
      tts: FakeTts(),
      sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
        calls++;
        return 'answer';
      },
      screenReaderActive: () => true,
      estimateReadTime: (_) => const Duration(milliseconds: 50),
      useMockQuery: true,
      mockQuery: 'q',
    );

    final first = controller.handleTap();
    await controller.handleTap(); // ignored while busy
    await first;

    expect(calls, 1);
  });

  group('voiceSemanticLabel', () {
    test('every state has a distinct, non-empty label', () {
      final labels = <String>[
        voiceSemanticLabel(VoiceState.idle),
        voiceSemanticLabel(VoiceState.listening),
        voiceSemanticLabel(VoiceState.thinking),
        voiceSemanticLabel(VoiceState.speaking, answer: 'A'),
        voiceSemanticLabel(VoiceState.error, error: 'E'),
      ];
      expect(labels.toSet().length, labels.length);
      expect(labels.every((l) => l.isNotEmpty), isTrue);
    });

    test('speaking and error labels carry the answer / reason', () {
      expect(voiceSemanticLabel(VoiceState.speaking, answer: 'Paris.'),
          contains('Paris.'));
      expect(voiceSemanticLabel(VoiceState.error, error: 'No mic.'),
          contains('No mic.'));
    });
  });

  // ---- Phase 3: settings-gated behaviors -----------------------------------

  group('agent-change announcement (announceAgentChanges)', () {
    test('ON (no reader): specialist spoken via flutter_tts, BRAIN suppressed',
        () async {
      final tts = FakeTts();
      final announced = <String>[];
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'BRAIN'});
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'SHOPPING'});
          return 'The answer.';
        },
        screenReaderActive: () => false,
        settings: SettingsController(), // announceAgentChanges defaults true
        announce: announced.add,
      );

      await controller.handleTap();

      expect(tts.spoken, contains('SHOPPING agent active.'));
      expect(tts.spoken, contains('The answer.'));
      expect(tts.spoken, isNot(contains('BRAIN agent active.'))); // router
      expect(announced, isEmpty); // no reader → not the live-region path
    });

    test('OFF: no agent utterance (only the answer is spoken)', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'SHOPPING'});
          return 'The answer.';
        },
        screenReaderActive: () => false,
        settings: SettingsController()..announceAgentChanges = false,
        announce: (_) {},
      );

      await controller.handleTap();

      expect(tts.spoken, <String>['The answer.']);
    });

    test('effective-reader path announces via the live region, NOT flutter_tts',
        () async {
      final tts = FakeTts();
      final announced = <String>[];
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'SHOPPING'});
          return 'The answer.';
        },
        // No OS reader, but the manual override forces the defer path on.
        screenReaderActive: () => false,
        settings: SettingsController()..screenReaderMode = true,
        estimateReadTime: (_) => Duration.zero,
        announce: announced.add,
      );

      await controller.handleTap();

      expect(announced, contains('SHOPPING agent active.'));
      expect(tts.spoken, isEmpty); // one-voice rule: nothing via flutter_tts
    });

    test('no settings ⇒ no announcement (identical to pre-Phase-3)', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async {
          onWorking?.call(<String, dynamic>{'type': 'status', 'agent': 'SHOPPING'});
          return 'The answer.';
        },
        screenReaderActive: () => false,
      );

      await controller.handleTap();

      expect(tts.spoken, <String>['The answer.']);
    });
  });

  group('manual screen-reader override (screenReaderMode)', () {
    test('ON (no OS reader) ⇒ silent/defer path: answer NOT spoken', () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'The answer.',
        screenReaderActive: () => false,
        settings: SettingsController()..screenReaderMode = true,
        estimateReadTime: (_) => Duration.zero,
      );

      await controller.handleTap();

      expect(controller.state, VoiceState.idle);
      expect(tts.spoken, isEmpty); // deferred to the live region
    });

    test('OFF (no OS reader) ⇒ flutter_tts speaks the answer (unchanged)',
        () async {
      final tts = FakeTts();
      final controller = VoiceController(
        speech: FakeSpeech(result: 'hi'),
        tts: tts,
        sendQuery: (String t, {void Function(Map<String, dynamic>)? onWorking}) async => 'The answer.',
        screenReaderActive: () => false,
        settings: SettingsController(), // screenReaderMode defaults false
      );

      await controller.handleTap();

      expect(tts.spoken, <String>['The answer.']);
    });
  });
}
