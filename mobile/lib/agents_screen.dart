/// The Agents tab (Phase 2).
///
/// A standard accessible, scrollable screen (NOT the Chat tab's single-button
/// model): the section header "BRAIN / AGENTS", the five agent cards built from
/// the shared agent model ([AgentKind] / [AgentInfo]), the reusable
/// [ReasoningFlow] panel in its reference/idle state (all steps "waiting", 0/5),
/// and an "OpenSight v1.0" footer.
///
/// Accessibility: the agent cards are a semantic LIST of buttons, each labeled
/// with its name + sub-label; the reasoning steps keep their Phase-1 ordered-list
/// semantics (provided by [ReasoningFlow] itself).
library;

import 'package:flutter/material.dart';

import 'ui/app_theme.dart';
import 'ui/reasoning_flow.dart';

/// Scrollable Agents screen body (rendered below the shared header by the shell).
class AgentsScreen extends StatelessWidget {
  const AgentsScreen({super.key, this.highContrast = false});

  /// When true, secondary text resolves to its high-contrast variant.
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    // Reduce-motion: the reasoning panel here is static (idle reference state),
    // but pass the flag through so its indicators render their static frame.
    final bool reduceMotion = MediaQuery.of(context).disableAnimations;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          const ExcludeSemantics(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text('BRAIN / AGENTS', style: AppText.sectionHeader),
            ),
          ),
          // The five agent cards as a semantic list of buttons.
          Semantics(
            container: true,
            label: 'Agents',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                for (final AgentKind kind in AgentKind.values) ...<Widget>[
                  _AgentCard(kind: kind, highContrast: highContrast),
                  if (kind != AgentKind.values.last)
                    const SizedBox(height: 10),
                ],
              ],
            ),
          ),
          const SizedBox(height: 20),
          // Reuse the ReasoningFlow panel in its reference/idle state: every step
          // "waiting", counter 0/5.
          ReasoningFlow(
            completedSteps: 0,
            showActive: false,
            reduceMotion: reduceMotion,
          ),
          const SizedBox(height: 20),
          ExcludeSemantics(
            child: Center(
              child: Text('OpenSight v1.0',
                  style: AppText.captionFor(highContrast)),
            ),
          ),
        ],
      ),
    );
  }
}

/// One agent card: a status dot in the agent color, the name in the agent color,
/// the gray sub-label, and a trailing line icon + chevron, on a rounded surface.
///
/// Accessibility: the whole card is a single [Semantics] button labeled with the
/// agent name + sub-label; its decorative visuals are excluded.
class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.kind, this.highContrast = false});

  final AgentKind kind;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    final AgentInfo info = AgentInfo.of(kind);
    return Semantics(
      button: true,
      label: '${info.name}, ${info.subLabel}',
      child: ExcludeSemantics(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(kRadius),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            children: <Widget>[
              // Status dot in the agent's color.
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: info.color,
                ),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      info.name,
                      style: AppText.body.copyWith(
                        color: info.color,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(info.subLabel,
                        style: AppText.captionFor(highContrast)),
                  ],
                ),
              ),
              // Trailing line icon (the agent's glyph) + chevron.
              Icon(info.icon, color: AppColors.textDim, size: 20),
              const SizedBox(width: 8),
              const Icon(Icons.chevron_right,
                  color: AppColors.textDim, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}
