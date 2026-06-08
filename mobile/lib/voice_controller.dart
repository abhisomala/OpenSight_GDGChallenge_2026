/// State machine + flow controller for the accessible voice screen.
///
/// Phase 4 wires real voice in/out: a tap records speech (speech_to_text, FINAL
/// result only), sends it through the `/ws` engine client, then speaks the
/// answer (flutter_tts) — unless a screen reader is active, in which case the
/// app defers to it (see the serialization note on [_announce]). The five
/// states are:
///
///   idle → listening → thinking → speaking → idle
///
/// with any speech/permission/transport problem going to a recoverable `error`
/// state (a tap from `error` returns to `idle`). All error messages are audible.
///
/// A build-time [config.useMockQuery] flag sends a preset query instead of
/// opening the mic, so demos/emulators without working audio still have a
/// reliable single-tap trigger (no extra UI/gesture).
library;

import 'dart:async';

import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';

import 'config.dart' as config;
import 'engine_client.dart';
import 'settings_controller.dart';
import 'speech_service.dart';
import 'tts_service.dart';

/// The five UI states. `listening` is live mic capture; `thinking` covers the
/// `/ws` round trip; `speaking` plays the answer back.
enum VoiceState { idle, listening, thinking, speaking, error }

/// Signature of [EngineClient.sendQuery], so a fake can be injected in tests.
typedef SendQuery = Future<String> Function(
  String text, {
  void Function(Map<String, dynamic> frame)? onWorking,
});

/// True when a platform screen reader (TalkBack / VoiceOver) is driving the UI.
bool _platformScreenReaderActive() => WidgetsBinding
    .instance.platformDispatcher.accessibilityFeatures.accessibleNavigation;

/// Best-effort reading time for the screen-reader path, where the OS gives no
/// "finished speaking" callback. Length-based, with a floor so short answers
/// aren't cut off and a ceiling so we never hang.
Duration _defaultEstimateReadTime(String text) =>
    Duration(milliseconds: (text.length * 55).clamp(1500, 15000).toInt());

/// Default live-region announcement to the platform screen reader. Kept separate
/// from flutter_tts to preserve the one-voice rule on the effective-reader path.
///
/// Uses `SemanticsService.announce`: its non-deprecated successor
/// (`sendAnnouncement`) requires a `FlutterView`, which this context-free
/// controller has no handle to — `announce` is the right context-free seam here.
void _defaultAnnounceToReader(String message) {
  // ignore: deprecated_member_use
  SemanticsService.announce(message, TextDirection.ltr);
}

/// Drives the [VoiceState] machine and the record → query → speak flow.
class VoiceController extends ChangeNotifier {
  VoiceController({
    SendQuery? sendQuery,
    SpeechService? speech,
    TtsService? tts,
    bool Function()? screenReaderActive,
    Duration Function(String text)? estimateReadTime,
    SettingsController? settings,
    void Function(String message)? announce,
    this.useMockQuery = config.useMockQuery,
    this.mockQuery = config.mockQuery,
  })  : _sendQuery = sendQuery ?? EngineClient().sendQuery,
        _speech = speech ?? SttSpeechService(),
        _tts = tts ?? FlutterTtsService(),
        _screenReaderActive = screenReaderActive ?? _platformScreenReaderActive,
        _estimateReadTime = estimateReadTime ?? _defaultEstimateReadTime,
        // Not an initializing formal: Dart forbids private NAMED params
        // (`this._settings`), and `settings` must stay the public arg name.
        // ignore: prefer_initializing_formals
        _settings = settings,
        _announceToReader = announce ?? _defaultAnnounceToReader;

  final SendQuery _sendQuery;
  final SpeechService _speech;
  final TtsService _tts;
  final bool Function() _screenReaderActive;
  final Duration Function(String text) _estimateReadTime;

  /// Live settings, or null. When null, every gated behavior below is IDENTICAL
  /// to the pre-Phase-3 default, so existing tests need no change.
  final SettingsController? _settings;

  /// Posts a polite live-region announcement to the platform screen reader
  /// (seam so tests can observe it without a real reader). Used for the
  /// agent-change announcement on the effective-screen-reader path.
  final void Function(String message) _announceToReader;

  /// When true, skip the mic and send [mockQuery] (build-time demo fallback).
  final bool useMockQuery;

  /// Preset query used when [useMockQuery] is true.
  final String mockQuery;

  VoiceState _state = VoiceState.idle;
  VoiceState get state => _state;

  String _responseText = '';

  /// Last answer from a `response` frame (shown/announced while speaking).
  String get responseText => _responseText;

  String _lastQuery = '';

  /// Last user query text (the words sent to the engine). Exposed so the Chat
  /// view can render the "YOU" conversation bubble alongside the [responseText]
  /// "OPENSIGHT" bubble. This is a VIEW-only accessor — it does not affect the
  /// state machine, transitions, or any other flow logic.
  String get lastQuery => _lastQuery;

  String _errorMessage = '';

  /// Friendly, user-facing reason for the current error (shown/announced).
  String get errorMessage => _errorMessage;

  /// Last specialist agent announced during the current query (so each agent is
  /// announced at most once). Reset at the start of every query.
  String _lastAnnouncedAgent = '';

  bool _disposed = false;

  /// Effective screen-reader mode = a real OS reader OR the manual
  /// `screenReaderMode` setting. The manual toggle can only ADD the defer path
  /// (logical OR) — it can never force speech when an OS reader is present.
  /// With no settings, this is exactly [_screenReaderActive] (unchanged).
  bool _effectiveScreenReader() =>
      _screenReaderActive() || (_settings?.screenReaderMode ?? false);

  /// Single entry point for taps. `idle` starts a query; `error` resets to
  /// `idle`; while busy (`listening`/`thinking`/`speaking`) taps are ignored.
  Future<void> handleTap() async {
    switch (_state) {
      case VoiceState.idle:
        await _runQuery();
      case VoiceState.error:
        _set(VoiceState.idle);
      case VoiceState.listening:
      case VoiceState.thinking:
      case VoiceState.speaking:
        break; // busy mid-exchange — ignore taps
    }
  }

  Future<void> _runQuery() async {
    _set(VoiceState.listening);

    // 1. Obtain the query text — from the mic, or the preset mock query.
    final String query;
    if (useMockQuery) {
      query = mockQuery;
    } else {
      try {
        final bool ready = await _speech.initialize();
        if (!ready) {
          await _toError('Microphone permission is needed.');
          return;
        }
        final String heard = await _speech.listenOnce();
        if (heard.trim().isEmpty) {
          await _toError("I didn't catch that.");
          return;
        }
        query = heard;
      } on SpeechException catch (e) {
        await _toError(e.permissionDenied
            ? 'Microphone permission is needed.'
            : "I didn't catch that.");
        return;
      }
    }

    // 2. Send to the engine. Working frames keep us in `thinking`.
    _lastQuery = query; // view-only: lets the Chat screen show the "YOU" bubble
    _lastAnnouncedAgent = ''; // start a fresh agent-announcement window
    _set(VoiceState.thinking);
    final String answer;
    try {
      answer = await _sendQuery(
        query,
        onWorking: (Map<String, dynamic> frame) {
          if (_state != VoiceState.thinking) _set(VoiceState.thinking);
          _maybeAnnounceAgent(frame); // settings-gated; no-op when settings null
        },
      );
    } on EngineConnectionException {
      await _toError("I couldn't reach the server.");
      return;
    } catch (_) {
      await _toError('Something went wrong.');
      return;
    }

    // 3. Speak the answer, then return to idle.
    _responseText = answer;
    _set(VoiceState.speaking);
    await _announce(answer);
    _set(VoiceState.idle);
  }

  /// Speak [text] without ever colliding with a screen reader.
  ///
  /// Serialization: only ONE voice is active at a time. When a screen reader is
  /// active it owns the audio channel — the app stays silent (the live-region
  /// label is what TalkBack reads) and we wait an estimated reading time, since
  /// the platform exposes no screen-reader completion callback. When no screen
  /// reader is active, flutter_tts speaks and its completion gates the wait.
  Future<void> _announce(String text) async {
    if (_effectiveScreenReader()) {
      await Future<void>.delayed(_estimateReadTime(text));
    } else {
      await _tts.speak(text);
    }
  }

  /// Move to the recoverable error state with a [friendly] message that is made
  /// audible (spoken by flutter_tts unless a screen reader will announce it).
  Future<void> _toError(String friendly) async {
    _errorMessage = friendly;
    _set(VoiceState.error);
    if (!_effectiveScreenReader()) {
      await _tts.speak(friendly);
    }
  }

  /// Announce a newly active SPECIALIST agent from a `status`/`research_status`
  /// frame's `agent` field. Gated on `announceAgentChanges` and a no-op when
  /// `_settings` is null. BRAIN is suppressed (it's the router that always fires
  /// first; announcing it would just collide with the specialist it routes to).
  ///
  /// One-voice rule preserved: on the effective-screen-reader path it posts a
  /// polite live-region announcement (NO flutter_tts); otherwise it speaks via
  /// fire-and-forget flutter_tts (not awaited, so timing/transitions are intact).
  void _maybeAnnounceAgent(Map<String, dynamic> frame) {
    final SettingsController? settings = _settings;
    if (settings == null || !settings.announceAgentChanges) return;

    final Object? agent = frame['agent'];
    if (agent is! String) return;
    final String name = agent.trim();
    if (name.isEmpty ||
        name.toUpperCase() == 'BRAIN' ||
        name == _lastAnnouncedAgent) {
      return;
    }
    _lastAnnouncedAgent = name;

    final String message = '$name agent active.';
    if (_effectiveScreenReader()) {
      _announceToReader(message); // live region — defer, no second voice
    } else {
      _tts.speak(message); // fire-and-forget; do NOT await
    }
  }

  void _set(VoiceState next) {
    if (_disposed) return;
    _state = next;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _speech.dispose();
    _tts.dispose();
    super.dispose();
  }
}
