/// The "REASONING FLOW  X / 5" panel: a titled card with five step rows, each
/// showing a leading status indicator + the step title + a sub-status.
///
/// Used on the Chat processing/speaking states now, and reused on the Agents tab
/// in Phase 2. Purely presentational — the caller supplies how many steps are
/// complete and whether the next step is active; this widget renders. It holds
/// no timers and drives no progression itself.
///
/// Status rendering (per the Phase 1 prompt):
///   DONE    = green check + "done"
///   ACTIVE  = cyan spinner + bold title + "active"
///   WAITING = gray hollow circle + "waiting"
library;

import 'package:flutter/material.dart';

import 'app_theme.dart';

/// The five reasoning steps, in order. Shared so the Agents tab (Phase 2) reuses
/// the exact same labels.
const List<String> kReasoningSteps = <String>[
  'Classify intent',
  'Extract constraints',
  'Route to agent',
  'Execute task',
  'Generate response',
];

/// A reasoning-flow card driven by [completedSteps] (0–5).
///
/// The "X / 5" counter reflects [completedSteps]; rows below that count are DONE.
/// When [showActive] is true and not all steps are complete, the next step
/// (index == [completedSteps]) renders as ACTIVE; otherwise it is WAITING.
///
/// [reduceMotion] swaps the ACTIVE spinner for a static indicator so the card is
/// stable under `MediaQuery.disableAnimations`.
class ReasoningFlow extends StatelessWidget {
  const ReasoningFlow({
    super.key,
    required this.completedSteps,
    this.showActive = true,
    this.reduceMotion = false,
  });

  final int completedSteps;
  final bool showActive;
  final bool reduceMotion;

  @override
  Widget build(BuildContext context) {
    final int done = completedSteps.clamp(0, kReasoningSteps.length);
    final int activeIndex =
        (showActive && done < kReasoningSteps.length) ? done : -1;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(kRadius),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          // Title + "X / 5" counter.
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: <Widget>[
              const Text('REASONING FLOW', style: AppText.sectionHeader),
              Text(
                '$done / ${kReasoningSteps.length}',
                style: AppText.sectionHeader,
              ),
            ],
          ),
          const SizedBox(height: 12),
          for (int i = 0; i < kReasoningSteps.length; i++) ...<Widget>[
            _StepRow(
              index: i,
              total: kReasoningSteps.length,
              title: kReasoningSteps[i],
              status: i < done
                  ? _StepStatus.done
                  : (i == activeIndex ? _StepStatus.active : _StepStatus.waiting),
              reduceMotion: reduceMotion,
            ),
            if (i != kReasoningSteps.length - 1) const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

enum _StepStatus { done, active, waiting }

/// One step row: leading indicator + title + sub-status text.
///
/// The indicators are deliberately MUTED/outlined and lower-contrast (per the
/// Figma reference) so the panel reads as secondary — DONE is an outlined check
/// in a dimmed green (not a bright filled circle), WAITING is a thin dim hollow
/// circle. ACTIVE keeps the single cyan accent so the current step stands out.
///
/// Accessibility: the row is exposed as one ordered-list item via [Semantics]
/// (`Step N of M: <title>, <status>`); its decorative inner widgets are excluded.
class _StepRow extends StatelessWidget {
  const _StepRow({
    required this.index,
    required this.total,
    required this.title,
    required this.status,
    required this.reduceMotion,
  });

  final int index;
  final int total;
  final String title;
  final _StepStatus status;
  final bool reduceMotion;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Step ${index + 1} of $total: $title, $_subStatus',
      child: ExcludeSemantics(
        child: Row(
          children: <Widget>[
            SizedBox(width: 20, height: 20, child: Center(child: _indicator())),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                title,
                style: switch (status) {
                  // Current step is the one focal accent.
                  _StepStatus.active => AppText.body.copyWith(
                      color: AppColors.cyan, fontWeight: FontWeight.bold),
                  // Done/waiting titles stay muted so the panel reads secondary.
                  _StepStatus.done =>
                    AppText.body.copyWith(color: AppColors.textDim),
                  _StepStatus.waiting => AppText.body.copyWith(
                      color: AppColors.textDim.withValues(alpha: 0.7)),
                },
              ),
            ),
            Text(_subStatus, style: AppText.caption.copyWith(color: _subColor)),
          ],
        ),
      ),
    );
  }

  Widget _indicator() {
    switch (status) {
      case _StepStatus.done:
        // Outlined, dimmed green — muted, not a bright filled check.
        return Icon(Icons.check_circle_outline,
            color: AppColors.stepDone.withValues(alpha: 0.55), size: 18);
      case _StepStatus.active:
        // Reduce-motion: a static marker instead of the spinning ring.
        return reduceMotion
            ? const Icon(Icons.adjust, color: AppColors.stepActive, size: 18)
            : const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor:
                      AlwaysStoppedAnimation<Color>(AppColors.stepActive),
                ),
              );
      case _StepStatus.waiting:
        // Thin, dim hollow circle.
        return Container(
          width: 16,
          height: 16,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
              color: AppColors.stepWaiting.withValues(alpha: 0.6),
              width: 1.5,
            ),
          ),
        );
    }
  }

  String get _subStatus => switch (status) {
        _StepStatus.done => 'done',
        _StepStatus.active => 'active',
        _StepStatus.waiting => 'waiting',
      };

  Color get _subColor => switch (status) {
        _StepStatus.done => AppColors.stepDone.withValues(alpha: 0.6),
        _StepStatus.active => AppColors.stepActive,
        _StepStatus.waiting => AppColors.stepWaiting.withValues(alpha: 0.7),
      };
}
