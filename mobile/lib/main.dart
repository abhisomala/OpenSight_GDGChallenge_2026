import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'config.dart';
import 'firebase_options.dart';
import 'home_shell.dart';
import 'ui/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // All Firebase use is gated on [requireAuth] (mirrors the server's
  // REQUIRE_AUTH). When it is false we touch no Firebase code at all, so the app
  // runs exactly as before with zero Firebase at runtime.
  if (requireAuth) {
    try {
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
      // Anonymous sign-in gives us an ID token to send on each /ws connection.
      await FirebaseAuth.instance.signInAnonymously();
    } catch (e) {
      // Do not crash the app if init / sign-in fails (e.g. offline) — log and
      // continue. A later /ws connection simply won't have a token to send.
      debugPrint('OpenSight: Firebase anonymous sign-in failed: $e');
    }
  }

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
