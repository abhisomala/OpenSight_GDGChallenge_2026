/// The shared OpenSight header bar, rendered consistently across all tabs.
///
/// Extracted (verbatim) from the Phase-1 Chat screen's private `_Header` so the
/// nav shell can render one header above every tab. It shows the OpenSight logo
/// (the app icon, converted from .ico to a bundled PNG), the "OpenSight" title +
/// tagline, and a round ⋮ button with a cyan focus ring. The ⋮ is a focus-ringed
/// PLACEHOLDER for now (model selection lives in the Settings tab, Phase 3) — it
/// is decorative so taps still fall through to whatever is behind it.
library;

import 'package:flutter/material.dart';

import 'app_theme.dart';

/// Full-width header: logo + brand title + tagline + placeholder ⋮.
class AppHeader extends StatelessWidget {
  const AppHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 12, 12),
      child: Row(
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.asset(
              'assets/images/opensight_logo.png',
              width: 32,
              height: 32,
              fit: BoxFit.cover,
            ),
          ),
          const SizedBox(width: 12),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: const <Widget>[
              Text('OpenSight', style: AppText.brandTitle),
              SizedBox(height: 2),
              Text('Technology that Adapts to You', style: AppText.tagline),
            ],
          ),
          const Spacer(),
          // Placeholder ⋮ button — focus-ringed, no action yet.
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.surface,
              border: Border.all(color: AppColors.cyan, width: 2),
            ),
            child: const Icon(Icons.more_vert,
                color: AppColors.textPrimary, size: 20),
          ),
        ],
      ),
    );
  }
}
