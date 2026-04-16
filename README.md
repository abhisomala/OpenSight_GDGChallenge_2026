# OpenSight

**Technology that Adapts to You.**

> An AI-powered voice assistant that replaces screen readers with active, intent-driven task execution — navigating, searching, and acting on behalf of visually impaired users.

*Google Developer Groups on Campus Solution Challenge 2026 · Sustainable Development Goal 10 · Sustainable Development Goal 3*

---

## Demo

> **[▶ Watch the 2-minute demo](https://youtube.com/your-link-here)**

Demo flow: *"Find me research on omega-3 and brain health"* → Google Scholar tab opens → *"Find me a supplement for that under $30"* → Amazon opens automatically, cross-agent memory carries the research context forward → *"Open the first one"* → Product page opens and ingredients are scraped live. Three utterances. No repetition. No manual navigation.

---

## The Problem

**2.2 billion people** worldwide have a vision impairment (WHO, 2023), of whom 39 million are blind. The tools built to help them haven't fundamentally changed in decades.

Screen readers process interfaces **linearly** — reading every element from top to bottom. The result:

- Blind web users lose an average of **30.4% of their time** to frustrating screen reader situations — confusing layout feedback, conflicts with applications, missing alt text *(Lazar et al., International Journal of Human-Computer Interaction)*
- **97% of the web remains inaccessible** to the disabled community *(AudioEye, 2024 — scan of ~40,000 enterprise websites)*
- Blind users attempting Fortune 500 job applications succeeded only **55.6% of the time** — the shortest application took 20 minutes, the longest took **135 minutes** *(Journal of Visual Impairment & Blindness, 2023)*

This is not a niche problem. It is a systemic exclusion from the modern web.

---

## The Solution

OpenSight replaces passive reading with **active task execution**.

Users speak naturally. OpenSight understands intent, navigates autonomously, and speaks results back — without the user ever touching a keyboard or memorizing a shortcut.

**Stanford University** found speech input is **3× faster than keyboard** (161 vs 53 WPM) with a 20.4% lower error rate. OpenSight is built on that insight end-to-end.

### What makes it different

**Cross-agent memory** — After a research query, OpenSight automatically carries that context into a follow-up shopping search. The user says *"find me a supplement for that"* — OpenSight already knows what "that" is.

**Live page awareness** — When a product page opens, OpenSight scrapes it in real time. Asking *"what are the ingredients"* returns the actual ingredient list from the open page, not a generic web search.

**Wake word activation** — Say *"OpenSight"* from anywhere and the app comes to the foreground, ready to listen. Browser windows step aside automatically; OpenSight reclaims focus when you speak to it.

---

## Architecture

```
User speaks
    │
    ▼
Deepgram Nova-2 STT ── real-time streaming speech to text
    │
    ▼
OpenSight server ── FastAPI WebSocket · SessionMemory · browser_manager
    │
    ▼
Gemini 2.5 Flash router ── intent classification · preference extraction
    │
    ├──► Shopping agent ──► Playwright → Amazon (scrapes results + product pages)
    │
    ├──► Research agent ──► SerpAPI → Google Scholar (extracts product_hint for handoff)
    │
    ├──► Calendar agent ──► Google Calendar API (read + create events)
    │
    └──► General agent ──► Google Custom Search API + Gemini synthesis
    │
    ▼
ElevenLabs TTS ── spoken response streamed back to user
```

### How it works

**Routing** — Every utterance passes through Gemini 2.5 Flash which classifies intent and decides which agent handles it. Shopping and research follow-ups are detected and short-circuited before Gemini, preserving context without extra API calls.

**Cross-agent handoff** — `SessionMemory` persists across all agents and WebSocket reconnects. When the Research agent finds papers on omega-3, it extracts a clean `product_hint` and stores it. When the user says *"find me a supplement for that under $30"*, the router detects the research context and builds the Amazon query automatically.

**Browser lifecycle** — All browser windows are managed through a central `browser_manager` registry. Opening Amazon closes Scholar. Opening a product page closes Amazon. When the user says the wake word, `browser_manager.focus_opensight()` snaps the desktop app back to the foreground via Win32 `SetForegroundWindow`.

**Live scraping** — When a product page opens, Playwright scrapes ingredient fields and feature bullets before handing control to the user. Follow-up questions about the open product are answered from scraped data, not a web search.

---

## Scalability & Future Vision

### Designed to scale

OpenSight is built around two decisions that make it inherently extensible.

The **multi-agent architecture** means adding a new capability — email, file management, IDE control, music — is just adding a new agent file and a routing rule in `router.py`. The voice pipeline, memory system, and WebSocket server are fully decoupled from what agents do. The system currently has five agents; it could have fifty without touching the core.

It ships today as a **standalone desktop application** — zero install friction beyond one Python file. The FastAPI backend and WebSocket transport are already decoupled from the client, meaning the server could be hosted remotely with no client-side changes. A cloud-hosted version, a mobile client, or a browser extension are all direct extensions of the existing architecture. The always-on wake word loop means OpenSight already functions as a background accessibility layer — the foundation for full OS-level control across any application.

### Near-term roadmap

- Full OS-level control — IDE navigation, file management, email
- Cross-application memory — preferences and context that survive across sessions and apps
- Mobile client — same agent backend, voice interface on iOS/Android
- Braille display output — parallel text channel alongside voice
- Real user testing — structured evaluation with visually impaired participants

---

## Google Developer Groups on Campus — Google Technologies Used

| Technology | How OpenSight uses it |
|---|---|
| **Gemini 2.5 Flash** | Intent routing on every utterance, response synthesis, preference extraction, cross-agent reasoning, follow-up detection |
| **Google Custom Search API** | Powers the General agent — web search for any query that doesn't require Amazon, Scholar, or Calendar |
| **Google Calendar API** | The Calendar agent reads and creates events via OAuth |
| **Google Scholar** (via SerpAPI) | Academic paper search for the Research agent, with automatic product keyword extraction for cross-agent handoff |

---

## Sustainable Development Goals Addressed

### SDG 10 — Reduced Inequalities *(primary)*

OpenSight directly targets the digital accessibility gap. Visually impaired users are systematically excluded from the efficiency gains of modern web interfaces — e-commerce, research tools, scheduling platforms. By replacing linear screen reading with intent-driven navigation, OpenSight reduces the time and cognitive load gap between sighted and visually impaired users.

97% of the web is inaccessible. OpenSight doesn't wait for the web to fix itself — it navigates it as-is, on behalf of the user.

**Measurable target:** Reduce task completion time for common shopping and research flows from 8+ minutes (NVDA screen reader baseline) to under 60 seconds.

### SDG 3 — Good Health and Well-Being *(secondary)*

Independence is directly correlated with mental health outcomes for people with disabilities. Tools that reduce reliance on sighted assistance — and eliminate the documented frustration of inaccessible interfaces — contribute to autonomy, confidence, and well-being. OpenSight requires zero prior technical training and zero memorized keyboard shortcuts.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice input | Deepgram Nova-2 real-time STT |
| LLM | Gemini 2.5 Flash |
| Agent orchestration | Python (custom multi-agent loop) |
| Browser automation | Playwright (Chromium) |
| Voice output | ElevenLabs TTS |
| Backend | FastAPI + WebSockets |
| Desktop UI | Tkinter (custom LiquidGlass renderer) |
| Memory | JSON persistence + in-memory `SessionMemory` |
| Window management | Win32 ctypes (`SetForegroundWindow`) |

---

## Setup

### Prerequisites

- Python 3.11+
- Windows (Win32 focus management) or macOS (partial support)
- A microphone

### Installation

```bash
git clone https://github.com/YOUR_USERNAME/opensight
cd opensight
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
playwright install chromium
```

### Environment variables

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_key_here
DEEPGRAM_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here

# Google Calendar (OAuth)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret

# Google Custom Search (General agent)
GOOGLE_SEARCH_API_KEY=your_key_here
GOOGLE_SEARCH_CX=your_cx_here

# SerpAPI (Research agent)
SERPAPI_KEY=your_key_here
```

For Google Calendar OAuth, download `credentials.json` from Google Cloud Console and place it in the project root. `token.json` is generated on first run.

---

## Running

Open two terminals with the virtual environment active:

**Terminal 1 — Backend server**
```bash
uvicorn server:app --host 127.0.0.1 --port 8080
```

**Terminal 2 — Desktop app**
```bash
python desktop_app.py
```

Say **"OpenSight"** to activate, or click the orb, or press **Space**.

---

## Full Demo Script

Speak these in sequence to see every system working together:

1. *"Find me research on omega-3 and brain health"* — Research agent, Scholar tab opens
2. *"Can you find me a supplement for that under $30"* — cross-agent handoff, Amazon opens
3. *"Open the first one"* — product page opens, ingredients scraped in background
4. *"What are the ingredients"* — answered from the live page, not a web search

Each turn is handled by a different agent. Memory carries forward automatically across all four.

---

## Project Structure

```
opensight/
├── agents/
│   ├── router.py          # Gemini intent classifier + cross-agent detection
│   ├── shopping.py        # Amazon browser agent + live page scraping
│   ├── research.py        # Google Scholar agent + product_hint extraction
│   ├── calendar.py        # Google Calendar API agent
│   └── general.py         # Google Custom Search + Gemini synthesis
├── ui/
│   ├── ui_draw.py         # Canvas rendering + agent rail
│   ├── ui_context.py      # Context panel + About You pills + Documents
│   ├── ui_animations.py   # Waveform, typing cursor, gradient loops
│   └── ui_theme.py        # Dark/light color system
├── assets/
│   └── icons/
├── docs/
│   ├── memory.md
│   └── roadmap.md
├── server.py              # FastAPI WebSocket server + session persistence
├── desktop_app.py         # Main app entry point + wake word integration
├── memory.py              # SessionMemory + cross-session JSON persistence
├── audio_engine.py        # Deepgram STT + ElevenLabs TTS + wake word loop
├── browser_manager.py     # Cross-agent browser lifecycle + Win32 focus control
└── app_state.py           # Shared UI + agent state
```

---

## Team

Built for the **Google Developer Groups on Campus Solution Challenge 2026**

*Virginia Tech*

---

## License

MIT