/// The Chat voice screen.
///
/// History: Phase 3 made the whole screen a single accessible button; Phase 1 of
/// the redesign restyled it. This refinement evolves it into a CHAT screen — a
/// scrollable conversation (YOU / OPENSIGHT bubbles) with the reasoning-flow
/// panel below it and the mic button at the bottom — and evolves the
/// accessibility model accordingly (the original prompt's single-button model is
/// intentionally retired here):
///
///   * the conversation is a LIVE LOG: each message is a [Semantics] live region
///     so a screen reader announces new messages politely;
///   * the reasoning steps are an ORDERED LIST (see `reasoning_flow.dart`);
///   * the MIC is the primary [Semantics] button, carrying the per-state label.
///
/// A full-screen [GestureDetector] still routes taps to `handleTap` for sighted,
/// eyes-free convenience, but it is no longer a semantic button. [HapticFeedback]
/// still fires on every state change, and every animation is gated on
/// `MediaQuery.disableAnimations` (reduce-motion) so a motion-sensitive or
/// screen-reader user gets a static final frame.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'settings_controller.dart';
import 'ui/app_theme.dart';
import 'ui/agent_banner.dart';
import 'ui/reasoning_flow.dart';
import 'voice_controller.dart';

/// Per-state semantic label for the button. Pure (no widget state) so it can be
/// unit-tested directly. "Double tap" matches how TalkBack users activate.
///
/// In `speaking`/`error` the label carries the [answer]/[error] text so that a
/// screen reader, which the app defers to instead of using flutter_tts, reads
/// the actual answer or the reason aloud via the live region.
String voiceSemanticLabel(
  VoiceState state, {
  String answer = '',
  String error = '',
}) {
  switch (state) {
    case VoiceState.idle:
      return 'Idle. Double tap to ask a question.';
    case VoiceState.listening:
      return 'Listening. Speak now.';
    case VoiceState.thinking:
      return 'Thinking. Please wait.';
    case VoiceState.speaking:
      return answer.isNotEmpty ? answer : 'Speaking the answer.';
    case VoiceState.error:
      return error.isNotEmpty
          ? '$error Double tap to try again.'
          : 'Something went wrong. Double tap to try again.';
  }
}

/// Default agent shown in the processing banner.
///
/// NOTE: this is a SCRIPTED VISUAL only. The processing state's reasoning-step
/// progression and this banner are NOT yet wired to real backend status frames.
/// The engine already emits `status` frames carrying an `agent` field (delivered
/// to the controller via `onWorking`), but surfacing that to the view requires a
/// small VoiceController change to expose the current agent / step — that wiring
/// is a LATER step, deliberately NOT part of this view-only phase.
const AgentKind _kDefaultProcessingAgent = AgentKind.brain;

/// Full-screen accessible voice screen driven by a [VoiceController].
class VoiceScreen extends StatefulWidget {
  const VoiceScreen({super.key, required this.controller, this.settings});

  final VoiceController controller;

  /// Optional live settings (Phase 3). Read here ONLY for view concerns — the
  /// haptic-feedback gate and high-contrast text. Null ⇒ haptics on, normal
  /// contrast (identical to before Phase 3).
  final SettingsController? settings;

  @override
  State<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends State<VoiceScreen>
    with TickerProviderStateMixin {
  // Animation controllers, each tied to exactly one VoiceState. They are started
  // and stopped by [_syncAnimations] (never run in the wrong state) and disposed
  // in [dispose]. Under reduce-motion they never start (a static frame renders).
  late final AnimationController _glow; // listening: pulse ring
  late final AnimationController _reasoning; // thinking: scripted 0→5 progression

  /// Cached reduce-motion flag (from `MediaQuery.disableAnimations`), refreshed
  /// in [didChangeDependencies].
  bool _reduceMotion = false;

  @override
  void initState() {
    super.initState();
    _glow = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1300),
    );
    // ~0.8s per visual step across 6 stops (0→5); swept once per `thinking`.
    _reasoning = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 4800),
    );
    widget.controller.addListener(_onStateChanged);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reduceMotion = MediaQuery.of(context).disableAnimations;
    _syncAnimations();
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onStateChanged);
    _glow.dispose();
    _reasoning.dispose();
    super.dispose();
  }

  /// True when text should render in the high-contrast variant.
  bool get _highContrast => widget.settings?.highContrastText ?? false;

  void _onStateChanged() {
    // Haptic confirmation on every state change (accessibility requirement) —
    // a stronger cue for the terminal/answer states. Gated on the haptic-feedback
    // setting (default on ⇒ unchanged); skip the platform call when it is off.
    if (widget.settings?.hapticFeedback ?? true) {
      switch (widget.controller.state) {
        case VoiceState.error:
          HapticFeedback.heavyImpact();
        case VoiceState.speaking:
          HapticFeedback.mediumImpact();
        case VoiceState.idle:
        case VoiceState.listening:
        case VoiceState.thinking:
          HapticFeedback.selectionClick();
      }
    }
    setState(() {}); // rebuild for the new label / visuals
    _syncAnimations(); // run/stop controllers for the new state
  }

  /// Run exactly the controller(s) appropriate for the current state (and only
  /// when motion is allowed); stop the rest. Idempotent — safe to call often.
  void _syncAnimations() {
    final VoiceState state = widget.controller.state;
    _toggleRepeat(_glow, run: !_reduceMotion && state == VoiceState.listening);

    // Reasoning: a single monotonic 0→5 sweep on entering `thinking`, so the
    // active marker advances and completed steps accrue checks (instead of
    // resetting on a loop). Stopped and rewound when not thinking; under
    // reduce-motion it never runs (a static mid-flow frame renders instead).
    if (!_reduceMotion && state == VoiceState.thinking) {
      if (!_reasoning.isAnimating && !_reasoning.isCompleted) {
        _reasoning.forward(from: 0);
      }
    } else {
      if (_reasoning.isAnimating) _reasoning.stop();
      if (state != VoiceState.thinking) _reasoning.value = 0;
    }
  }

  void _toggleRepeat(AnimationController c, {required bool run}) {
    if (run) {
      if (!c.isAnimating) c.repeat();
    } else if (c.isAnimating) {
      c.stop();
    }
  }

  @override
  Widget build(BuildContext context) {
    final VoiceState state = widget.controller.state;
    // The nav shell (home_shell.dart) now provides the Scaffold, the shared
    // AppHeader, and the SafeArea above this tab. This widget is just the Chat
    // tab body — its behavior, states, animations, and accessibility are
    // unchanged from Phase 1.
    //
    // Tap-anywhere convenience for sighted/eyes-free use. NOT a semantic node:
    // the mic button below is the screen's primary button for screen readers.
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.controller.handleTap,
      child: Container(
        width: double.infinity,
        height: double.infinity,
        color: AppColors.bgBase,
        child: Column(
          children: <Widget>[
            Expanded(child: _content(state)),
            _bottomControls(state),
          ],
        ),
      ),
    );
  }

  // ---- Content area (conversation + reasoning, or the idle prompt) ----------

  Widget _content(VoiceState state) {
    if (state == VoiceState.error) return _errorView();

    final bool hasTurn = widget.controller.lastQuery.isNotEmpty;
    if (!hasTurn) {
      // No turn yet: keep the original idle prompt (decorative — the mic button
      // label conveys the same to a screen reader). Brightens under high contrast.
      return ExcludeSemantics(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              'Tap the microphone below and speak your request.',
              textAlign: TextAlign.center,
              style: _highContrast
                  ? AppText.body.copyWith(
                      color: AppColors.textPrimaryHigh,
                      fontWeight: FontWeight.w600,
                    )
                  : AppText.body.copyWith(color: AppColors.textDim),
            ),
          ),
        ),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _conversation(state),
          // The reasoning-flow panel stays BELOW the conversation, while a turn
          // is in flight (thinking) or being read back (speaking).
          if (state == VoiceState.thinking) ...<Widget>[
            const SizedBox(height: 16),
            const AgentBanner(kind: _kDefaultProcessingAgent),
            const SizedBox(height: 12),
            // Rebuild as the scripted sweep advances; under reduce-motion the
            // controller is stopped, so a stable representative frame renders.
            AnimatedBuilder(
              animation: _reasoning,
              builder: (BuildContext context, _) => ReasoningFlow(
                completedSteps: _reasoningCompleted(VoiceState.thinking),
                showActive: true,
                reduceMotion: _reduceMotion,
              ),
            ),
          ] else if (state == VoiceState.speaking) ...<Widget>[
            const SizedBox(height: 16),
            // speaking (INFERRED — TO-CONFIRM against Figma): the reasoning flow
            // stays shown and complete (5/5) while the answer is read.
            ReasoningFlow(
              completedSteps: _reasoningCompleted(VoiceState.speaking),
              showActive: false,
              reduceMotion: _reduceMotion,
            ),
          ],
        ],
      ),
    );
  }

  /// The conversation: the user's query bubble, and (once available) the
  /// assistant's answer bubble. The big central waveform/brand mark is gone.
  Widget _conversation(VoiceState state) {
    final VoiceController c = widget.controller;
    // Show the answer once it exists and the turn has reached/finished speaking
    // (during `thinking` the answer isn't ready, and any prior answer is stale).
    final bool showAnswer = c.responseText.isNotEmpty &&
        (state == VoiceState.speaking || state == VoiceState.idle);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _Bubble(
          speaker: 'YOU',
          text: c.lastQuery,
          isUser: true,
          highContrast: _highContrast,
        ),
        if (showAnswer) ...<Widget>[
          const SizedBox(height: 12),
          _Bubble(
            speaker: 'OPENSIGHT',
            text: c.responseText,
            isUser: false,
            highContrast: _highContrast,
          ),
        ],
      ],
    );
  }

  Widget _errorView() {
    final String reason = widget.controller.errorMessage;
    // Decorative: the mic button's per-state label already conveys the reason +
    // "double tap to try again" to a screen reader.
    return ExcludeSemantics(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            const Icon(Icons.error_outline, size: 72, color: AppColors.error),
            const SizedBox(height: 20),
            Text(
              reason.isNotEmpty
                  ? reason
                  : 'Something went wrong — tap to try again',
              textAlign: TextAlign.center,
              style: AppText.body,
            ),
            if (reason.isNotEmpty) ...<Widget>[
              const SizedBox(height: 8),
              Text(
                'Tap to try again',
                textAlign: TextAlign.center,
                style: AppText.caption.copyWith(color: AppColors.amber),
              ),
            ],
          ],
        ),
      ),
    );
  }

  /// Completed-step count for the reasoning panel.
  ///
  /// speaking → 5/5 (complete). thinking → the scripted 0→5 sweep driven by
  /// [_reasoning]; under reduce-motion (controller stopped) a stable mid-flow
  /// frame so the static UI still reads as "in progress".
  int _reasoningCompleted(VoiceState state) {
    if (state == VoiceState.speaking) return kReasoningSteps.length;
    if (_reduceMotion) return 2;
    // 6 stops (0..5) across the controller's 0→1 sweep.
    return (_reasoning.value * (kReasoningSteps.length + 1))
        .floor()
        .clamp(0, kReasoningSteps.length);
  }

  // ---- Bottom controls (mic button + label + caption) ----------------------

  Widget _bottomControls(VoiceState state) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          // The mic is THE primary semantic button: it carries the per-state
          // label and routes activation to the controller. Its visual contents
          // are decorative and excluded.
          Semantics(
            button: true,
            label: voiceSemanticLabel(
              state,
              answer: widget.controller.responseText,
              error: widget.controller.errorMessage,
            ),
            onTap: widget.controller.handleTap,
            child: ExcludeSemantics(child: _micButton(state)),
          ),
          const SizedBox(height: 16),
          ExcludeSemantics(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  _buttonLabel(state),
                  textAlign: TextAlign.center,
                  style: AppText.body.copyWith(
                    color: _labelColor(state),
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                  ),
                ),
                if (state == VoiceState.idle) ...<Widget>[
                  const SizedBox(height: 8),
                  Text(
                    'Gemini · Deepgram · Google TTS',
                    textAlign: TextAlign.center,
                    style: AppText.captionFor(_highContrast),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// The 88×88 gradient mic button, with a state-specific glow/contents. The
  /// button visual mirrors state; activation is handled by the [Semantics]
  /// wrapper and the screen-level tap.
  Widget _micButton(VoiceState state) {
    final bool listening = state == VoiceState.listening;
    final bool thinking = state == VoiceState.thinking;

    // Gradient: amber→orange while processing, otherwise blue→purple.
    final List<Color> colors = thinking
        ? const <Color>[AppColors.amber, AppColors.orange]
        : const <Color>[AppColors.micGradStart, AppColors.micGradEnd];

    final Color glow = thinking
        ? AppColors.amber
        : (listening ? AppColors.cyan : Colors.transparent);

    final Widget core = AnimatedContainer(
      duration:
          _reduceMotion ? Duration.zero : const Duration(milliseconds: 250),
      width: 88,
      height: 88,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: LinearGradient(
          colors: colors,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        boxShadow: <BoxShadow>[
          if (glow != Colors.transparent)
            BoxShadow(
              color: glow.withValues(alpha: 0.55),
              blurRadius: 24,
              spreadRadius: 2,
            ),
        ],
      ),
      child: Center(child: _micButtonChild(state)),
    );

    // Listening pulse ring behind the button (animated, or static under
    // reduce-motion). No ring otherwise.
    if (listening) {
      return SizedBox(
        width: 128,
        height: 128,
        child: Stack(
          alignment: Alignment.center,
          children: <Widget>[_pulseRing(), core],
        ),
      );
    }
    return core;
  }

  Widget _micButtonChild(VoiceState state) {
    switch (state) {
      case VoiceState.thinking:
        // Processing spinner (white). Under reduce-motion, a static glyph.
        return _reduceMotion
            ? const Icon(Icons.hourglass_empty, color: Colors.white, size: 32)
            : const SizedBox(
                width: 32,
                height: 32,
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                ),
              );
      case VoiceState.listening:
        return const Icon(Icons.mic_off, color: Colors.white, size: 36);
      case VoiceState.idle:
      case VoiceState.speaking:
      case VoiceState.error:
        return const Icon(Icons.mic, color: Colors.white, size: 36);
    }
  }

  /// Cyan pulse ring for the listening state. Expands + fades on a loop while
  /// `_glow` runs; renders a single static ring under reduce-motion.
  Widget _pulseRing() {
    if (_reduceMotion) {
      return Container(
        width: 112,
        height: 112,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppColors.cyan.withValues(alpha: 0.18),
        ),
      );
    }
    return AnimatedBuilder(
      animation: _glow,
      builder: (BuildContext context, _) {
        final double t = _glow.value; // 0→1
        return Container(
          width: 88 + 40 * t,
          height: 88 + 40 * t,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.cyan.withValues(alpha: 0.45 * (1 - t)),
          ),
        );
      },
    );
  }

  String _buttonLabel(VoiceState state) {
    switch (state) {
      case VoiceState.idle:
        return 'Tap microphone to speak';
      case VoiceState.listening:
        return 'LISTENING — tap to stop';
      case VoiceState.thinking:
        return 'PROCESSING…';
      case VoiceState.speaking:
        return 'SPEAKING';
      case VoiceState.error:
        return 'Something went wrong — tap to try again';
    }
  }

  Color _labelColor(VoiceState state) {
    switch (state) {
      case VoiceState.listening:
        return AppColors.cyan;
      case VoiceState.thinking:
        return AppColors.amber;
      case VoiceState.error:
        return AppColors.error;
      case VoiceState.idle:
      case VoiceState.speaking:
        return AppColors.textPrimary;
    }
  }
}

/// One conversation bubble: a small uppercase mono speaker label over the message
/// text, aligned right for the user ("YOU") and left for the assistant
/// ("OPENSIGHT").
///
/// Accessibility: the whole bubble is a single live region that announces the
/// new message politely ("You said: …" / "OpenSight said: …"); its decorative
/// inner widgets are excluded.
class _Bubble extends StatelessWidget {
  const _Bubble({
    required this.speaker,
    required this.text,
    required this.isUser,
    this.highContrast = false,
  });

  final String speaker;
  final String text;
  final bool isUser;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    final Color bg = isUser
        ? AppColors.cyan.withValues(alpha: 0.12)
        : AppColors.surface;
    final Color borderColor =
        isUser ? AppColors.cyan.withValues(alpha: 0.4) : AppColors.border;

    return Semantics(
      liveRegion: true,
      label: '${isUser ? 'You said' : 'OpenSight said'}: $text',
      child: ExcludeSemantics(
        child: FractionallySizedBox(
          alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
          widthFactor: 0.85,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(kRadius),
              border: Border.all(color: borderColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(speaker, style: AppText.sectionHeader),
                const SizedBox(height: 4),
                Text(text, style: AppText.bodyFor(highContrast)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
