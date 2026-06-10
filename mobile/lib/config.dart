/// Static configuration for the OpenSight voice client.
library;

/// WebSocket URL of the OpenSight backend `/ws` endpoint.
///
/// Default targets the deployed Cloud Run backend, so the app works on
/// emulators and physical devices without a laptop-hosted server.
///
/// For local development against a backend on the developer's laptop, use the
/// emulator line below: `10.0.2.2` is the Android emulator's special alias for
/// the host machine's loopback (`127.0.0.1`). On a real physical device,
/// `10.0.2.2` does NOT work — use the laptop's LAN IP instead
/// (e.g. `ws://192.168.1.42:8080/ws`) with phone and laptop on the same network.
///
/// Path mirrors the desktop client's `/ws` endpoint from CONTRACT.md §1.
// const String engineUrl = 'ws://10.0.2.2:8080/ws'; // local dev (Android emulator)
const String engineUrl = 'wss://opensight-backend-348346331222.us-east1.run.app/ws';

/// Build-time fallback for demos / emulators where the microphone may not
/// capture reliably. When `true`, a tap sends [mockQuery] through the engine
/// client INSTEAD of opening the mic; when `false` (default) a tap records real
/// speech (Phase 4).
///
/// This is a config flag ONLY — it adds no new UI or gesture, so the single
/// full-screen tap target stays exactly the same. Flip it to `true` for a
/// reliable trigger when running on an emulator without working audio input.
const bool useMockQuery = false;

/// Preset query used when [useMockQuery] is `true`.
const String mockQuery = "what's the capital of France";

/// Whether the client must authenticate to the backend `/ws` endpoint.
///
/// Mirrors the server's `REQUIRE_AUTH` flag (`server.py`). When `true`, the app
/// initializes Firebase, signs in anonymously, and sends an auth frame carrying
/// the Firebase ID token as the FIRST message on each `/ws` connection
/// (before the `{"text": ...}` query). When `false` (default) the app runs with
/// zero Firebase at runtime and sends no auth frame — byte-for-byte the original
/// behavior. Keep this in sync with the server's `REQUIRE_AUTH`.
const bool requireAuth = false;
