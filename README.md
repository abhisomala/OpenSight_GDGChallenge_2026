# OpenSight

**Technology that Adapts to You.**

> An AI-powered voice assistant that replaces screen readers with active, intent-driven task execution: navigating, searching, and acting on behalf of visually impaired users.

*Google Developer Groups on Campus Solution Challenge 2026 · Sustainable Development Goal 10 · Sustainable Development Goal 3*

---

## Demo

> **[▶ Watch the 2-minute demo](https://youtu.be/UOYZ2oXvdvM)** where OpenSight opens a browser and completes the task live.

Three spoken sentences take the user from a research question to a chosen product. The video shows the assistant opening a browser and driving the live web end to end, advancing its reasoning in real time as it goes. Cross-agent memory carries context across tasks, with zero manual navigation. The full step-by-step demo script lives in [DEMO.md](DEMO.md).

---

## Repository structure

This is a monorepo with two clients on one backend:

- **Repo root:** the desktop engine and backend, including the FastAPI WebSocket server (`server.py`), the multi-agent system (`agents/`), the Tkinter desktop UI (`ui/`, `desktop_app.py`), audio/voice (`audio_engine.py`), and browser automation (`desktop_browser.py`). This is the primary OpenSight application.
- **`mobile/`:** the Flutter Android voice client, a thin "voice in, text over `/ws`, voice out" front end that talks to the same backend. It contains no agent or model code; the engine does all the work. The `/ws` message contract both clients implement lives in [CONTRACT.md](CONTRACT.md).

---

## The Problem

**2.2 billion people** worldwide have a vision impairment (WHO, 2023), of whom 39 million are blind. The tools built to help them have not fundamentally changed in decades.

Screen readers process interfaces **linearly**, reading every element from top to bottom. The result:

- Blind web users lose an average of **30.4% of their time** to frustrating screen reader situations including confusing layout feedback, conflicts with applications, and missing alt text *(Lazar et al., International Journal of Human-Computer Interaction)*
- **97% of the web remains inaccessible** to the disabled community *(AudioEye, 2024, scan of ~40,000 enterprise websites)*
- Blind users attempting Fortune 500 job applications succeeded only **55.6% of the time**. The shortest application took 20 minutes, the longest took **135 minutes** *(Journal of Visual Impairment & Blindness, 2023)*

This is not a niche problem. It is a systemic exclusion from the modern web.

---

## The Results

OpenSight completes the same product research and selection task **5x faster than the average screen reader user, and up to 10x faster for a first-time user**, reducing a 5-10 minute task to under 60 seconds.

| User type | NVDA baseline | OpenSight | Speedup |
|---|---|---|---|
| Beginner (self-measured, first NVDA use) | ~10 min | ~60 sec | **~10x** |
| Average *(Lazar et al., published literature)* | ~5 min | ~60 sec | **~5x** |
| Expert *(published literature)* | ~2 min | ~60 sec | **~2x** |

The beginner baseline was measured directly: with no prior NVDA experience, completing the same omega-3 supplement search task on Amazon took approximately 10 minutes. OpenSight completed the identical task in under 60 seconds. This is an **80-90% reduction in interaction time**. The gain is not speed of speech. It is the elimination of navigation overhead entirely.

---

## The Solution

OpenSight replaces passive reading with **active task execution**.

Users speak naturally. OpenSight understands intent, navigates autonomously, and speaks results back without the user ever touching a keyboard or memorizing a shortcut.

**Stanford University** found speech input is **3x faster than keyboard** (161 vs 53 WPM) with a 20.4% lower error rate. OpenSight is built on that insight end to end.

### What makes it different

There are two relevant categories of existing tools, and OpenSight is distinct from each on a different axis.

**Versus screen readers (NVDA, JAWS, VoiceOver):** these read interfaces linearly, carry no context between tasks, and require the user to drive every step. They describe a page. They do not search, filter, compare, or act. OpenSight executes the task and speaks back only the result.

**Versus agentic browsers and assistants (for example ChatGPT Atlas):** these can perform multi-step browser actions and carry context across tasks, so "agentic" alone is not the distinction. The difference is who they are built for. Agent mode in tools like Atlas is designed to be supervised visually: it narrates what it is doing, pauses for the user to watch on sensitive steps, and assumes the user can see the screen and take over. That interaction model presumes sight. These tools have also drawn early criticism from the blind community for poor screen reader accessibility in their own interfaces. OpenSight is built to be operated entirely without sight: voice in, a spoken answer out, a wake word instead of a cursor, and no visual surface to monitor.

OpenSight does all of this with a single spoken sentence per step.

**Cross-agent memory:** After a research query, OpenSight automatically carries that context into a follow-up shopping search. The user says *"find me a supplement for that"* and OpenSight already knows what "that" is. No existing screen reader or voice assistant does this for a non-sighted user end to end.

**Live page awareness:** When a product page opens, OpenSight scrapes it in real time. Asking *"what are the ingredients"* returns the actual ingredient list from the open page, not a generic web search.

**Wake word activation:** Say *"OpenSight"* from anywhere and the app comes to the foreground, ready to listen. Browser windows step aside automatically. OpenSight reclaims focus when you speak to it.

---

## Interface

![OpenSight UI - reasoning flow panel active during a research query](readme_assets/opensight_demo.gif)

*The desktop client (engine + Tkinter UI) during a research query.*

![The OpenSight Flutter Android voice client advancing through the reasoning flow during a voice request](mobile/readme_assets/opensight_mobile_demo.gif)

*The Flutter Android voice client (`mobile/`): a thin "voice in, text over `/ws`, voice out" front end on the same backend.*

---

## Architecture

```mermaid
flowchart TD
    A([User speaks]):::io --> B[Deepgram Nova-2 STT<br/><i>desktop</i>]
    B --> C[Firebase Authentication<br/><i>when enabled · user token, never a model key</i>]
    C --> D[OpenSight backend<br/><i>FastAPI WebSocket · SessionMemory · browser_manager</i>]
    D --> E[Gemini 2.5 Flash · Vertex AI<br/><i>intent classification · preference extraction</i>]

    E --> F[Shopping agent<br/>Playwright → Amazon]:::agent
    E --> G[Research agent<br/>SerpAPI → Google Scholar]:::agent
    E --> H[Calendar agent<br/>Google Calendar API]:::agent
    E --> I[General agent<br/>Google Custom Search + Gemini]:::agent

    F --> J[Google Cloud Text-to-Speech]:::io
    G --> J
    H --> J
    I --> J

    classDef io fill:#1f6feb,stroke:#1158c7,color:#ffffff
    classDef agent fill:#161b22,stroke:#30363d,color:#e6edf3
```

*The diagram shows the desktop pipeline. The Android client performs speech-to-text and text-to-speech on-device; everything from the WebSocket inward is identical.*

### How it works

**No client holds the model key:** Clients talk only to the backend, which holds the Vertex AI credentials and makes every Gemini call itself. When authentication is enabled, the backend verifies a Firebase ID token before accepting a connection, so access is gated by per-user identity rather than a shared key. Server-side verification is implemented and the Android client signs in with Firebase Anonymous Auth and presents its token; enforcement sits behind a feature flag, and extending the same handshake to the desktop client is on the near-term roadmap.

**Production model serving:** Gemini 2.5 Flash runs on Vertex AI, Google's production AI platform, giving production-grade quota and scaling rather than a rate-limited developer key. The credential is loaded server-side via Application Default Credentials.

**Routing:** Every utterance passes through Gemini 2.5 Flash, which classifies intent and decides which agent handles it. Follow-up queries are detected and short-circuited before Gemini using local pattern matching, preserving context without an extra model call.

**Cross-agent handoff:** `SessionMemory` persists across all agents and WebSocket reconnects. When the Research agent finds papers on a topic, it extracts a product hint and stores it. When the user says *"find me a supplement for that under $30"*, the router detects the research context and builds the Amazon query automatically. The product hint is produced by a Gemini call rather than a hardcoded keyword table, so the handoff generalizes to topics it was never explicitly coded for, not just the ones in the demo.

**Browser lifecycle:** All browser windows are managed through a central `browser_manager` registry. Opening Amazon closes Scholar. Opening a product page closes Amazon. When the wake word fires, `browser_manager.focus_opensight()` snaps the desktop app back to the foreground via Win32 `SetForegroundWindow`.

**Live scraping:** When a product page opens, Playwright waits for the result content to load, then scrapes ingredient fields and feature bullets before handing control to the user. Follow-up questions about the open product are answered from the scraped data, not a web search, so the spoken answer matches what is on the page.

---

## Validation

OpenSight is validated on two tracks: structured task testing, and direct engagement with the organizations and leaders who serve the blind and visually impaired (BVI) community.

### Task testing

Tested using simulated visual impairment methodology, a standard technique in HCI accessibility research where participants complete tasks without visual input to approximate the screen reader experience. This does not fully replicate the lived experience of blindness, and structured trials with BVI participants are the planned next phase.

**Self-measured baseline:** With no prior NVDA experience, the omega-3 supplement search task on Amazon took approximately 10 minutes. The identical task took under 60 seconds with OpenSight.

**Structured user testing (20 participants):**

- Average speed improvement rating: **7.9 / 10**
- Average navigation replacement rating: **7.8 / 10**
- Task completion rate: **20 / 20 participants completed the full four-step demo task without assistance**
- 80% said they would use a voice-first interface daily or for specific tasks

Three consistent feedback themes emerged: accent recognition accuracy (raised by 4 participants), response latency on complex queries (raised by 3 participants), and clearer audio cues for when to speak (raised by 2 participants). All three are on the active roadmap.

### Partnership and stakeholder validation

We are engaging directly with organizations and leaders in the BVI space to validate the problem, shape the product around real user needs, and run structured trials with BVI participants.

**Virginia Department for the Blind and Vision Impaired (DBVI):** We met with the Regional Manager, who helped us validate the problem and refine the product, and whose feedback directly informed planned low-vision support such as font scaling. A session with the Director of Rehabilitation Technology Services is scheduled for next month.

**Blind Institute of Technology (BIT):** We have an initial meeting scheduled with founder and Executive Director Mike Hess, a blind 20-year IT veteran. BIT places BVI professionals at Fortune 500 companies and its accessibility work has been featured at **Google Cloud Next 2019**.

Structured trials with blind and visually impaired participants are planned through these relationships as the next validation phase, moving beyond simulated testing to direct feedback from the community OpenSight is built for.

**Clean install verified:** The full setup from a fresh build has been tested and confirmed working.

---

## Scalability & Future Vision

### Built to scale

OpenSight is built around decisions that make it inherently extensible and ready for real users.

**Multi-agent architecture:** Adding a new capability (email, file management, IDE control, music) is just adding a new agent file and a routing rule in `router.py`. The voice pipeline, memory system, and WebSocket server are fully decoupled from what agents do. The system currently has four agents. It could have fifty without touching the core.

**Keyless clients, credentials in the backend:** No client embeds the model key; the backend makes every Gemini call. The Android client is a true thin client that carries no model credentials and talks to the backend over `/ws`. The desktop ships as a self-contained Windows application that runs the backend locally, so an end user installs nothing and provisions no keys. A containerized Cloud Run deployment is built as the path for the multi-user, mobile-facing backend, where each user is identified and gated individually with Firebase Authentication.

**Zero-friction distribution by design:** OpenSight ships as a standalone Windows executable. The end user downloads one `.exe`, double-clicks it, and says "OpenSight": no Python, no dependencies, no terminal, no keys to provision. This was an intentional scalability decision, not a convenience afterthought. The target user is a blind or visually impaired person, not a developer, so the distributed artifact has to behave like any ordinary consumer app. The full stack, including the voice pipeline, agent orchestration, and model access, is bundled and runs locally on the user's machine, so onboarding is a single download with nothing to configure. Reaching more users is a distribution problem, not a setup problem.

**Cross-platform reach (proof of concept):** A Flutter-based **Android client** has been built as a completed proof of concept. It is a thin, accessible, voice-first front end to the same backend, with on-device speech-to-text and text-to-speech, designed to be fully usable eyes-free with Android TalkBack. It was built phone-first on purpose: blind and visually impaired users rely overwhelmingly on phones with built-in screen readers, so the phone is the real distribution surface. iOS was intentionally excluded from this phase. That platform's permission model places inherent constraints on the always-listening microphone access and cross-application control that are central to OpenSight's design, whereas Android's more open model fits a voice-first, always-available assistant.

The always-on wake word loop means OpenSight already functions as a background accessibility layer, the foundation for full OS-level control across any application.

### Near-term roadmap

- Full OS-level control: IDE navigation, file management, email
- Cross-application memory: preferences and context that survive across sessions
- Low-vision support: font scaling and screen magnification alongside the voice-first flow
- Extend Firebase Authentication to the desktop client and enable enforcement by default, with Firebase App Check for hardening
- Cloud Run deployment for the multi-user, mobile-facing backend with persistent per-user memory
- Harden the Android proof of concept into a full release on the same agent backend
- Braille display output: a parallel text channel alongside voice
- Expanded structured trials with BVI participants through the DBVI and BIT relationships

---

## Google Developer Groups on Campus: Google Technologies Used

| Technology | How OpenSight uses it |
|---|---|
| **Gemini 2.5 Flash** | Intent routing on every utterance, response synthesis, preference extraction, cross-agent reasoning, follow-up detection |
| **Vertex AI** | Production serving for Gemini 2.5 Flash, called server-side via Application Default Credentials: production-grade quota, control, and scaling |
| **Firebase Authentication** | Per-user identity. Server-side ID-token verification is implemented and the Android client authenticates; enforcement is behind a feature flag, and the desktop client is on the roadmap |
| **Google Cloud Text-to-Speech** | Spoken responses on the desktop client (the Android client uses on-device text-to-speech) |
| **Google Cloud** | Application Default Credentials for server-side access to Google APIs, and Cloud Run as the containerized deployment path for the multi-user backend |
| **Google Custom Search API** | Powers the General agent for web search on any query that does not require Amazon, Scholar, or Calendar |
| **Google Calendar API** | The Calendar agent reads and creates events via OAuth |
| **Google Scholar** (via SerpAPI) | Academic paper search for the Research agent, with automatic product keyword extraction for cross-agent handoff |

---

## Sustainable Development Goals Addressed

### SDG 10: Reduced Inequalities *(primary)*

OpenSight directly targets the digital accessibility gap. Visually impaired users are systematically excluded from the efficiency gains of modern web interfaces including e-commerce, research tools, and scheduling platforms. By replacing linear screen reading with intent-driven navigation, OpenSight reduces the time and cognitive load gap between sighted and visually impaired users.

97% of the web is inaccessible. OpenSight does not wait for the web to fix itself. It navigates it as-is, on behalf of the user.

**Measurable outcome:** OpenSight completes a product research and selection task in under 60 seconds. That is 5x faster than the average screen reader user baseline and 10x faster than a beginner baseline, both measured under controlled conditions.

### SDG 3: Good Health and Well-Being *(secondary)*

Independence is directly correlated with mental health outcomes for people with disabilities. Tools that reduce reliance on sighted assistance and eliminate the documented frustration of inaccessible interfaces contribute to autonomy, confidence, and well-being. OpenSight requires zero prior technical training and zero memorized keyboard shortcuts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice input | Deepgram Nova-2 real-time STT (desktop); on-device STT (Android) |
| LLM | Gemini 2.5 Flash on Vertex AI (called server-side via Application Default Credentials) |
| Authentication | Firebase Authentication (per-user; server-side verification, enforcement behind a flag) |
| Agent orchestration | Python (custom multi-agent loop) |
| Browser automation | Playwright (Chromium) |
| Voice output | Google Cloud Text-to-Speech (desktop); on-device `flutter_tts` (Android) |
| Backend | FastAPI + WebSockets; bundled and run locally for the desktop `.exe`, with a Cloud Run deployment path for the mobile-facing backend |
| Desktop client | Tkinter (custom LiquidGlass renderer), packaged as a standalone Windows `.exe` |
| Mobile client | Android (Flutter), completed proof of concept; iOS excluded by design (platform permission constraints) |
| Memory | JSON persistence + in-memory SessionMemory |
| Window management | Win32 ctypes (SetForegroundWindow) |

---

## Get OpenSight

- **End users:** download the standalone Windows executable, run it, and say **"OpenSight."** No Python, no dependencies, no API keys.
- **Developers:** see **[SETUP.md](SETUP.md)** to install, configure Google Cloud and Firebase, and run from source.
- **Demo:** see **[DEMO.md](DEMO.md)** for the four-step demo script and reset flow.

---

## Team

Built for the **Google Developer Groups on Campus Solution Challenge 2026**

*Virginia Tech*