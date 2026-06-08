import 'package:flutter/material.dart';

import 'home_shell.dart';
import 'ui/app_theme.dart';

void main() {
  runApp(const MyApp());
}

/// Root of the OpenSight voice client. Hosts the [HomeShell], which owns the
/// single [VoiceController] and the 3-tab navigation (Chat / Agents / Settings).
/// The Chat tab records speech (or fires the preset mock query when that
/// fallback is enabled in config), sends it through the `/ws` engine client, and
/// speaks the answer back.
class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'OpenSight',
      debugShowCheckedModeBanner: false,
      // Shared dark theme (Phase 1 redesign). Screens paint their own surfaces
      // from AppColors; this keeps the app-level scaffold/background consistent
      // (e.g. before the first frame).
      theme: ThemeData(
        useMaterial3: true,
        brightness: Brightness.dark,
        scaffoldBackgroundColor: AppColors.bgBase,
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.cyan,
          brightness: Brightness.dark,
        ),
      ),
      home: const HomeShell(),
    );
  }
}
