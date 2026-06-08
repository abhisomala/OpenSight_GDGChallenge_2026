/// The app's navigation shell (Phase 2): a 3-tab bottom navigation —
/// Chat / Agents / Settings — with the shared header above every tab.
///
/// Ownership: the shell owns the single [VoiceController] so a tab switch never
/// recreates it. The tab bodies live in an [IndexedStack], which keeps every tab
/// alive — switching tabs does NOT dispose or reset the Chat conversation /
/// controller / animations.
///
/// Accessibility: the custom nav bar is hand-rolled to match the Figma's
/// icon+label-in-a-rounded-box look (Material's NavigationBar can't), but each
/// item is wrapped in [Semantics(button, selected, label)] so a screen reader
/// still announces the tab and whether it is selected — the semantics Material's
/// NavigationBar would have provided are preserved.
library;

import 'package:flutter/material.dart';

import 'agents_screen.dart';
import 'settings_controller.dart';
import 'settings_screen.dart';
import 'ui/app_header.dart';
import 'ui/app_theme.dart';
import 'voice_controller.dart';
import 'voice_screen.dart';

/// Root scaffold hosting the three tabs and the shared header.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key, this.controller, this.settings});

  /// Optional injected controller (for tests). When null, the shell creates,
  /// owns, and disposes its own; when provided, the caller retains ownership and
  /// the shell does NOT dispose it.
  final VoiceController? controller;

  /// Optional injected settings (for tests). Same ownership rule as [controller]:
  /// created+owned+disposed here when null; caller-owned when provided.
  final SettingsController? settings;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  late final SettingsController _settings;
  late final bool _ownsSettings;
  late final VoiceController _controller;
  late final bool _ownsController;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    // Settings first, so the controller we create can read them.
    _ownsSettings = widget.settings == null;
    _settings = widget.settings ?? SettingsController();
    _ownsController = widget.controller == null;
    // The owned controller is wired to settings so the three gated behaviors
    // (haptics/announce/screen-reader) react to the toggles. An injected
    // controller keeps whatever wiring the test gave it.
    _controller = widget.controller ?? VoiceController(settings: _settings);
  }

  @override
  void dispose() {
    // Only dispose what we created ourselves.
    if (_ownsController) _controller.dispose();
    if (_ownsSettings) _settings.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bgBase,
      body: SafeArea(
        child: Column(
          children: <Widget>[
            const ExcludeSemantics(child: AppHeader()),
            // IndexedStack keeps all tabs alive so switching preserves state.
            // Wrapped in a ListenableBuilder so a settings change (e.g. High
            // contrast) rebuilds every tab immediately.
            Expanded(
              child: ListenableBuilder(
                listenable: _settings,
                builder: (BuildContext context, _) {
                  final bool hc = _settings.highContrastText;
                  return IndexedStack(
                    index: _index,
                    children: <Widget>[
                      VoiceScreen(controller: _controller, settings: _settings),
                      AgentsScreen(highContrast: hc),
                      SettingsScreen(settings: _settings),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: _OpenSightNavBar(
        currentIndex: _index,
        onTap: (int i) => setState(() => _index = i),
      ),
    );
  }
}

/// Custom bottom nav: three items, each an icon + label inside a rounded box.
/// Active = cyan icon/label in a tinted focus box; inactive = gray. Built from
/// primitives (no new dependency) to match the Figma layout, with per-item
/// semantics preserved.
class _OpenSightNavBar extends StatelessWidget {
  const _OpenSightNavBar({required this.currentIndex, required this.onTap});

  final int currentIndex;
  final ValueChanged<int> onTap;

  static const List<_NavItem> _items = <_NavItem>[
    _NavItem('Chat', Icons.chat_bubble_outline),
    _NavItem('Agents', Icons.psychology_outlined),
    _NavItem('Settings', Icons.settings_outlined),
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.bgBase,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: <Widget>[
              for (int i = 0; i < _items.length; i++)
                _NavButton(
                  item: _items[i],
                  selected: i == currentIndex,
                  reduceMotion: MediaQuery.of(context).disableAnimations,
                  onTap: () => onTap(i),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _NavItem {
  const _NavItem(this.label, this.icon);
  final String label;
  final IconData icon;
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.item,
    required this.selected,
    required this.reduceMotion,
    required this.onTap,
  });

  final _NavItem item;
  final bool selected;
  final bool reduceMotion;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color accent = selected ? AppColors.cyan : AppColors.textDim;
    return Semantics(
      button: true,
      selected: selected,
      label: '${item.label} tab',
      child: ExcludeSemantics(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: AnimatedContainer(
            duration: reduceMotion
                ? Duration.zero
                : const Duration(milliseconds: 200),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              // Active tab sits in a tinted, cyan-outlined rounded focus box.
              color: selected
                  ? AppColors.cyan.withValues(alpha: 0.12)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(kRadius),
              border: Border.all(
                color: selected ? AppColors.cyan : Colors.transparent,
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(item.icon, color: accent, size: 20),
                const SizedBox(width: 8),
                Text(
                  item.label,
                  style: AppText.body.copyWith(
                    color: accent,
                    fontWeight: selected ? FontWeight.bold : FontWeight.normal,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
