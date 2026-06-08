# OpenSight Android — UI Design Spec (from Figma)

Source of truth for rebuilding the `voice_client` UI to match the Figma Make design.
Hand this to Claude Code. Color values are close approximations from the prototype —
pull exact hex from Figma Dev Mode if you want pixel-perfect tokens.

## The big scope note (read first)

The Figma design is a **three-tab app**, not the single screen the current app has:
a bottom navigation bar with **Chat**, **Agents**, and **Settings**. So this is a
redesign plus two new screens, not a reskin. Plan it in phases (below). The existing
`VoiceController` state machine and the accessibility model stay — they belong to the
Chat tab and must be preserved, not regenerated.

## Design language

- **Theme:** dark. Base background near-black navy (~`#0A0E17`). Cards/surfaces a touch
  lighter (~`#141A28`) with a subtle 1px border (~`#232A3B`), rounded corners ~16px.
- **Primary accent — cyan** (~`#22D3EE`): section headers, focus rings, the "OpenSight"
  waveform mark, the LISTENING label, active nav tab, toggles when on.
- **Mic button gradient:** blue → purple (~`#3B82F6` → `#8B5CF6`).
- **Agent accent colors:** BRAIN blue `#3B82F6`, SHOPPING green `#22C55E`, CALENDAR amber
  `#F59E0B`, RESEARCH purple `#A855F7`, GENERAL orange `#F97316`.
- **Text:** primary near-white (~`#E8EDF4`); secondary/dim gray (~`#8A93A6`) for captions,
  descriptions, and "Waiting for request".
- **Toggles:** ON = cyan track; OFF = gray track (~`#3A4150`).
- **Focus ring:** ~2px cyan outline on every interactive element (already a design rule).
- **Typography:** brand title "OpenSight" is a bold sans (~20px). Everything else uses a
  **monospace** typeface — section headers are uppercase, letter-spaced, cyan (~12px);
  body/labels/captions are mono (~13–15px). This mono treatment is core to the look.

## Components

- **Header bar** (all tabs): waveform brand icon, "OpenSight" title, "Technology that
  Adapts to You" tagline (cyan), and a round ⋮ icon button on the right with a cyan focus
  ring. (The ⋮ menu did not open a visible panel in the prototype; model selection lives
  in Settings, so the ⋮ menu can be omitted or wired later.)
- **Bottom nav**: three tabs — Chat (speech-bubble icon), Agents (brain icon), Settings
  (gear icon). Active = cyan icon + label inside a rounded focus box; inactive = gray.
- **Mic button**: 88×88 circle, blue→purple gradient, mic icon (idle) / mic-off icon
  (listening), with an animated cyan glow/pulse ring while listening.
- **Central status icon** (Chat): an outlined circle holding a speaker/waveform icon.
- **Agent card**: rounded surface, left status dot in the agent's color, name in the
  agent's color, gray sub-label, trailing line icon + chevron.
- **Reasoning step row**: a numbered badge (1–5) + step title + sub-status line.
- **Setting row**: title + gray description + iOS-style toggle; plus a model dropdown and
  read-only value rows (Deepgram, Google TTS).
- **About card**: key–value rows (App, Version, Platform, Build).

## Screens & states

### Chat tab — the voice screen (maps to the existing VoiceState enum)

- **idle**: dim outlined speaker icon; text "Tap the microphone below and speak your
  request."; mic button = gradient + mic icon; label "Tap microphone to speak"; caption
  "Gemini · Deepgram · Google TTS".
- **listening**: mic button = mic-off icon, brighter gradient + animated cyan glow/pulse
  ring; label "LISTENING — tap to stop" in cyan.
- **thinking** *(INFERRED — not captured live)*: reasoning-flow steps begin progressing
  and the active agent highlights; central area shows an indeterminate/working indicator;
  a "Thinking…" style label. Confirm the exact treatment from Figma or define it.
- **speaking** *(INFERRED — not captured live)*: the speaker/waveform icon animates while
  the response is read; response text is shown; a "Speaking" label. Confirm or define.
- **error** *(NOT in the Figma — define it)*: the design showed no error state. Define one
  in the same palette (amber/red accent, "Something went wrong — tap to try again"),
  consistent with the existing controller's recoverable error state.

### Agents tab

Header "BRAIN / AGENTS", then the five agent cards in order: BRAIN ("routing requests"),
SHOPPING ("scanning options"), CALENDAR ("checking schedules"), RESEARCH ("pulling
sources"), GENERAL ("composing responses"). Below: "REASONING FLOW  0 / 5" with five
steps — 1 Classify intent, 2 Extract constraints, 3 Route to agent, 4 Execute task,
5 Generate response — each "Waiting for request" when idle. Footer "OpenSight v1.0".

### Settings tab

- **MODEL CONFIGURATION**: Language Model dropdown (value "Gemini Pro"); Speech-to-Text
  read-only ("Deepgram"); Text-to-Speech read-only ("Google TTS").
- **ACCESSIBILITY**: four rows, each title + description + toggle —
    - Screen reader mode (ON) — "Enables verbose spoken feedback for all actions"
    - Announce agent changes (ON) — "Reads aloud when a new agent becomes active"
    - Haptic feedback (ON) — "Vibrates on microphone activation and response ready"
    - High contrast text (OFF) — "Increases text brightness to maximum"
- **ABOUT**: App = OpenSight, Version = 1.0.0, Platform = Android, Build = 2026.06.06.

## Animations

- **Listening glow**: continuous pulse ring around the mic (scale + opacity), ~1.2–1.5s
  loop, ease-in-out → `AnimationController` + `.repeat()`.
- **State transitions** (idle↔listening↔speaking, color/size/opacity): implicit animations
  — `AnimatedContainer`, `AnimatedOpacity`, `AnimatedSwitcher`, ~200–300ms.
- **Reasoning step activation**: each step badge fills with the active agent's color and
  gets a check on completion; animate the 0→5 progression.
- **Speaking**: animated waveform/pulse on the speaker icon while the answer is read.
- **Nav tab change**: color crossfade on the active tab.
- **Reduce motion**: gate every animation on `MediaQuery.disableAnimations` so motion-
  sensitive and screen-reader users get a static UI. For an accessibility product this is
  correct and a clean judge-facing detail.

## Build approach (preserve the accessibility work)

1. **Chat / voice screen restyle + animations** — highest value, it's the demo screen.
   Keep the existing `VoiceController` and the single-`Semantics`-button + live-region +
   haptics model. Put all the new visuals inside the existing `ExcludeSemantics` layer so
   they add zero screen-reader noise. Wire animations to `VoiceState`.
2. **Bottom nav + Agents screen** — add a `Scaffold` bottom nav (3 tabs). Agents/Settings
   are *standard* accessible scrollable screens (not the single-button model): the agents
   list is a semantic list, the reasoning steps an ordered list, matching the design's
   own a11y notes (role=log conversation, `<ol>` steps, `<ul>/<li>` agents,
   role=switch toggles).
3. **Settings screen** — render the model config and toggles. Wire toggles to real
   behavior where they map to existing code: Haptic feedback ↔ existing `HapticFeedback`;
   Screen reader mode / Announce agent changes ↔ existing TalkBack serialization; High
   contrast ↔ a theme switch. Don't ship dead toggles in the demo.

## Confirmed vs. inferred

- **Confirmed from the prototype**: idle, listening, the Agents screen (all five agent
  colors + the reasoning-flow layout), the full Settings screen, About, the bottom nav,
  the header, focus-ring behavior, and the palette by role.
- **Inferred / to confirm**: the thinking and speaking active-state visuals (couldn't be
  triggered without real mic audio), and the error state (absent from the design).