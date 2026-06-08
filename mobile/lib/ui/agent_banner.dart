/// A full-width pill announcing the active agent: icon + name + "— sub-label",
/// tinted by the agent's accent color.
///
/// Used on the Chat processing state now (under the header), and reused on the
/// Agents tab in Phase 2. Purely presentational — it takes an [AgentKind] and
/// renders; it holds no state and drives no behavior.
library;

import 'package:flutter/material.dart';

import 'app_theme.dart';

/// Full-width agent banner pill for [kind].
class AgentBanner extends StatelessWidget {
  const AgentBanner({super.key, required this.kind});

  final AgentKind kind;

  @override
  Widget build(BuildContext context) {
    final AgentInfo info = AgentInfo.of(kind);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        // A subtle tint of the agent accent, with a stronger accent border.
        color: info.color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(kRadius),
        border: Border.all(color: info.color.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: <Widget>[
          Icon(info.icon, color: info.color, size: 20),
          const SizedBox(width: 12),
          Text(
            info.name,
            style: AppText.body.copyWith(
              color: info.color,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              '— ${info.subLabel}',
              style: AppText.caption,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
