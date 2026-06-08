/// Static configuration for the OpenSight voice client.
library;

/// WebSocket URL of the OpenSight backend `/ws` endpoint.
///
/// Default targets the Android emulator: `10.0.2.2` is the emulator's special
/// alias for the host machine's loopback (`127.0.0.1`), so this reaches a backend
/// running on the developer's laptop at port 8080.
///
/// On a real physical device, `10.0.2.2` does NOT work — replace the host with the
/// laptop's LAN IP address (e.g. `ws://192.168.1.42:8080/ws`), and make sure the
/// phone and laptop are on the same network.
///
/// Path and port mirror the desktop client's default (`ws://127.0.0.1:8080/ws`)
/// from CONTRACT.md §1.
const String engineUrl = 'ws://10.0.2.2:8080/ws';

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
