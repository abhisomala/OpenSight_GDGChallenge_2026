# voice_client

A thin Flutter Android voice client for the OpenSight engine. It captures voice,
sends it to the FastAPI `/ws` endpoint over a WebSocket, and speaks the response
back. No agents, browser automation, or model code live here — the backend does
all of that. See `CLAUDE.md` for the full design and the locked decisions, and
the engine repo's `CONTRACT.md` for the `/ws` message contract.

This is an emulator-only POC.

---

## Prerequisites

- Flutter SDK at `C:\Users\somal\develop\flutter\bin` (not always on PATH —
  prepend it first). From PowerShell:
  ```powershell
  $env:Path = "C:\Users\somal\develop\flutter\bin;$env:Path"
  ```
- An Android emulator running (or a connected device — see notes below).
- The OpenSight backend reachable on port `8080` (see "Start the backend").

---

## 1. Point the client at the backend (`engineUrl`)

Edit `engineUrl` in `lib/config.dart`:

- **Android emulator (default):** `ws://10.0.2.2:8080/ws`. `10.0.2.2` is the
  emulator's alias for the host machine's loopback, so it reaches a backend
  running on your laptop.
- **Physical device:** `10.0.2.2` does NOT work. Use the laptop's LAN IP, e.g.
  `ws://192.168.1.42:8080/ws`, and make sure the phone and laptop are on the same
  network.

The scheme is `ws://` (cleartext); the manifest already allows cleartext traffic
for this dev setup.

## 2. Choose the input mode (`useMockQuery`)

Also in `lib/config.dart`:

- **`useMockQuery = false` (default):** a tap opens the microphone and sends your
  real spoken words. Needs working audio input (real device, or an emulator with a
  working mic).
- **`useMockQuery = true`:** a tap skips the mic and sends the preset `mockQuery`
  string (default: "what's the capital of France") through the engine instead.
  This is the reliable demo/emulator fallback when audio input isn't dependable.
  It is a config flag only — no extra UI or gesture; the screen stays a single
  full-screen tap target.

## 3. Start the backend on `0.0.0.0:8080`

In the OpenSight engine repo (`GDG2`), serve the FastAPI app bound to all
interfaces so the emulator/device can reach it:

```
uvicorn server:app --host 0.0.0.0 --port 8080
```

`0.0.0.0` (not `127.0.0.1`) is what lets `10.0.2.2` (emulator) or the LAN IP
(device) connect. The engine repo is read-only from this project's side — don't
modify it.

## 4. Run the app

```powershell
$env:Path = "C:\Users\somal\develop\flutter\bin;$env:Path"
flutter pub get
flutter run
```

Tap anywhere on the screen to ask a question. The screen cycles
idle → listening → thinking → speaking → idle, with haptics and a per-state
accessible label on each change.

---

## Tests and build

```powershell
$env:Path = "C:\Users\somal\develop\flutter\bin;$env:Path"
flutter analyze
flutter test
flutter build apk --debug
```

Tests in `test/` run on the host (no device): the `/ws` contract helpers, the
`VoiceController` state machine (including error recovery and the busy-tap guard),
and the `VoiceScreen` widget. There is no `integration_test/` suite — by policy,
live-backend round-trip checks belong in `test/`.

---

## Error handling and recovery

Every unhappy path lands in a single recoverable `error` state; the next tap
returns to `idle`. The error message is spoken aloud (unless a screen reader is
active, in which case the app stays silent and the live-region label is what
TalkBack reads). Covered paths:

- **Engine unreachable / connection timeout** — "I couldn't reach the server."
- **Mid-request disconnect** (socket closes before a `response` frame) — same.
- **No speech / unintelligible / STT error** — "I didn't catch that."
- **Microphone permission denied** — "Microphone permission is needed."

Two timeouts bound the otherwise-unbounded waits so a stall always recovers: the
`/ws` read guard (`defaultResponseTimeout`, 30s) fails a silent server as a
transport error, and the TTS completion fallback (`maxSpeakTimeout`, 30s) returns
to idle even if the speech engine never reports completion.

A rapid double-tap cannot start two concurrent requests: the first tap moves the
state machine out of `idle` synchronously, so any tap arriving mid-exchange is
ignored until the flow returns to `idle`.

---

## Accessibility note (built, hardware-unverified)

The full eyes-free loop — TalkBack on, live mic, exactly one voice active at a
time (the app defers to TalkBack and stays silent rather than colliding with it) —
is implemented but has only been exercised on an emulator. The TalkBack +
live-mic + no-collision behavior is **built but unverified on a physical device**,
which is out of scope for this POC.
