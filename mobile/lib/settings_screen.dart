/// The Settings tab (Phase 3) — the full Figma Settings screen, wired to the
/// shared [SettingsController].
///
/// Three sections: MODEL CONFIGURATION (a local-only model dropdown + two
/// read-only rows), ACCESSIBILITY (four iOS-style toggles bound to real
/// behavior), and an ABOUT card. Scrollable; the shared header is provided by
/// the nav shell. Rebuilds on settings changes via [ListenableBuilder].
library;

import 'package:flutter/material.dart';

import 'settings_controller.dart';
import 'ui/app_theme.dart';

/// Available language models for the (local-only) dropdown.
const List<String> _kModels = <String>['Gemini 2.5 Flash', 'Gemini Pro'];

/// Static About card values.
const String _kAppName = 'OpenSight';
const String _kVersion = '1.0.0';
const String _kPlatform = 'Android';
const String _kBuild = '2026.06.06';

/// Scrollable Settings screen body.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.settings});

  final SettingsController settings;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: settings,
      builder: (BuildContext context, _) {
        final bool hc = settings.highContrastText;
        return SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _sectionHeader('MODEL CONFIGURATION'),
              _ModelConfig(settings: settings, highContrast: hc),
              const SizedBox(height: 24),
              _sectionHeader('ACCESSIBILITY'),
              _AccessibilitySettings(settings: settings, highContrast: hc),
              const SizedBox(height: 24),
              _sectionHeader('ABOUT'),
              _AboutCard(highContrast: hc),
            ],
          ),
        );
      },
    );
  }

  Widget _sectionHeader(String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Text(text, style: AppText.sectionHeader),
      );
}

/// A rounded surface card wrapping settings rows.
class _Card extends StatelessWidget {
  const _Card({required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(kRadius),
        border: Border.all(color: AppColors.border),
      ),
      child: child,
    );
  }
}

/// Model dropdown (local-only) + read-only STT/TTS rows.
class _ModelConfig extends StatelessWidget {
  const _ModelConfig({required this.settings, required this.highContrast});

  final SettingsController settings;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          // Language Model — DISPLAY/LOCAL ONLY: the model is chosen server-side
          // and the /ws contract has no model field, so changing this never
          // sends anything to the backend; it only updates local state.
          Row(
            children: <Widget>[
              Expanded(
                child: Text('Language Model',
                    style: AppText.bodyFor(highContrast)),
              ),
              Semantics(
                label: 'Language Model',
                value: settings.geminiModel,
                child: DropdownButton<String>(
                  value: settings.geminiModel,
                  dropdownColor: AppColors.surface,
                  underline: const SizedBox.shrink(),
                  style: AppText.bodyFor(highContrast),
                  iconEnabledColor: AppColors.cyan,
                  items: <DropdownMenuItem<String>>[
                    for (final String m in _kModels)
                      DropdownMenuItem<String>(value: m, child: Text(m)),
                  ],
                  onChanged: (String? value) {
                    if (value != null) settings.geminiModel = value;
                  },
                ),
              ),
            ],
          ),
          const Divider(color: AppColors.border, height: 24),
          _ReadOnlyRow(
            title: 'Speech-to-Text',
            value: 'Deepgram',
            highContrast: highContrast,
          ),
          const SizedBox(height: 12),
          _ReadOnlyRow(
            title: 'Text-to-Speech',
            value: 'Google TTS',
            highContrast: highContrast,
          ),
        ],
      ),
    );
  }
}

/// A title + dim read-only value row.
class _ReadOnlyRow extends StatelessWidget {
  const _ReadOnlyRow({
    required this.title,
    required this.value,
    required this.highContrast,
  });

  final String title;
  final String value;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$title, $value',
      child: ExcludeSemantics(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: <Widget>[
            Text(title, style: AppText.bodyFor(highContrast)),
            Text(value, style: AppText.captionFor(highContrast)),
          ],
        ),
      ),
    );
  }
}

/// The four accessibility toggles.
class _AccessibilitySettings extends StatelessWidget {
  const _AccessibilitySettings({
    required this.settings,
    required this.highContrast,
  });

  final SettingsController settings;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        children: <Widget>[
          _ToggleRow(
            title: 'Screen reader mode',
            description: 'Enables verbose spoken feedback for all actions',
            value: settings.screenReaderMode,
            onChanged: (bool v) => settings.screenReaderMode = v,
            highContrast: highContrast,
          ),
          _divider(),
          _ToggleRow(
            title: 'Announce agent changes',
            description: 'Reads aloud when a new agent becomes active',
            value: settings.announceAgentChanges,
            onChanged: (bool v) => settings.announceAgentChanges = v,
            highContrast: highContrast,
          ),
          _divider(),
          _ToggleRow(
            title: 'Haptic feedback',
            description: 'Vibrates on microphone activation and response ready',
            value: settings.hapticFeedback,
            onChanged: (bool v) => settings.hapticFeedback = v,
            highContrast: highContrast,
          ),
          _divider(),
          _ToggleRow(
            title: 'High contrast text',
            description: 'Increases text brightness to maximum',
            value: settings.highContrastText,
            onChanged: (bool v) => settings.highContrastText = v,
            highContrast: highContrast,
          ),
        ],
      ),
    );
  }

  Widget _divider() => const Divider(color: AppColors.border, height: 24);
}

/// One accessibility toggle: title + description + an iOS-style switch.
///
/// Accessibility: the whole row is a single semantic switch
/// (`Semantics(toggled: value, label: title)`); its decorative visuals are
/// excluded, and toggling anywhere on the row flips the value.
class _ToggleRow extends StatelessWidget {
  const _ToggleRow({
    required this.title,
    required this.description,
    required this.value,
    required this.onChanged,
    required this.highContrast,
  });

  final String title;
  final String description;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      toggled: value,
      label: title,
      child: ExcludeSemantics(
        child: InkWell(
          onTap: () => onChanged(!value),
          child: Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(title, style: AppText.bodyFor(highContrast)),
                    const SizedBox(height: 2),
                    Text(description,
                        style: AppText.captionFor(highContrast)),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Switch(
                value: value,
                onChanged: onChanged,
                activeTrackColor: AppColors.cyan,
                inactiveTrackColor: AppColors.toggleOff,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Static About card: key–value rows.
class _AboutCard extends StatelessWidget {
  const _AboutCard({required this.highContrast});
  final bool highContrast;

  @override
  Widget build(BuildContext context) {
    return _Card(
      child: Column(
        children: <Widget>[
          _row('App', _kAppName),
          const SizedBox(height: 10),
          _row('Version', _kVersion),
          const SizedBox(height: 10),
          _row('Platform', _kPlatform),
          const SizedBox(height: 10),
          _row('Build', _kBuild),
        ],
      ),
    );
  }

  Widget _row(String key, String value) => Semantics(
        label: '$key, $value',
        child: ExcludeSemantics(
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: <Widget>[
              Text(key, style: AppText.captionFor(highContrast)),
              Text(value, style: AppText.bodyFor(highContrast)),
            ],
          ),
        ),
      );
}
