# CLAUDE.md — OpenSight Project Context

This file is the single source of truth for any AI assistant or new developer working on OpenSight. Read this before touching any file.

---

## What OpenSight Is

OpenSight is a voice-first, multi-agent AI accessibility system built for visually impaired and motor-disabled users. It replaces screen readers like NVDA with **active task execution** — users speak natural language and the system navigates browsers, searches APIs, and speaks results back.

**The core architectural insight:** Cross-agent memory. When a user researches omega-3 supplements and then says "find me one under $30", OpenSight already knows what "one" refers to. No existing screen reader, voice assistant, or browser agent (including ChatGPT Atlas) does this. This is not a feature — it is the design principle the entire system is built around.

**Competition context:** Top 10 finalist in the Google Developer Groups on Campus North America Solution Challenge 2026. SDG 10 (Reduced Inequalities) primary, SDG 3 (Good Health and Well-Being) secondary. Built at Virginia Tech. Mentorship with Google Developer Experts May 26–June 8. Resubmission follows. Demo Day at Google HQ late June/July 2026.

**Measured results:** 5–10x faster than screen readers. Task that takes a first-time NVDA user 10 minutes takes under 60 seconds with OpenSight.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Voice input | Deepgram Nova-2 real-time WebSocket STT |
| LLM | Gemini 2.5 Flash (routing + synthesis), Gemini 2.5 Pro (fallback) |
| Agent orchestration | Python, custom multi-agent loop |
| Browser automation | Playwright (Chromium) — runs locally only, not on Cloud Run |
| Voice output | Google Cloud TTS (streams via mpv) |
| Backend | FastAPI + WebSockets |
| Desktop UI | Tkinter (custom LiquidGlass renderer) |
| Memory | JSON persistence + in-memory SessionMemory |
| Window management | Win32 ctypes (SetForegroundWindow) |
| Cloud | Google Cloud Run (backend deployed, browser agents run locally) |

---

## File Hierarchy

```
GDG2/
├── agents/
│   ├── __init__.py
│   ├── router.py         # Gemini intent classifier. Every query hits this first.
│   │                     # Routes to SHOPPING, RESEARCH, CALENDAR, GENERAL.
│   │                     # generate_with_fallback() wraps Gemini in run_in_executor
│   │                     # so it doesn't block the FastAPI event loop.
│   ├── shopping.py       # Amazon browser agent. Opens Playwright Chromium,
│   │                     # scrapes search results, caches product details.
│   │                     # Handles follow-up selections ("open the first one").
│   │                     # CANNOT run on Cloud Run — requires local display.
│   ├── research.py       # Google Scholar via SerpAPI. Opens results in Chromium.
│   │                     # Extracts product_hint for cross-agent handoff to shopping.
│   │                     # CANNOT run on Cloud Run — requires local display.
│   ├── calendar.py       # Google Calendar API — reads and creates events.
│   │                     # Opens calendar.google.com via Playwright.
│   │                     # Requires credentials.json + token.json (OAuth).
│   └── general.py        # Google Custom Search + Gemini synthesis.
│                         # Answers from scraped product page data when Amazon is open.
│                         # Uses aiohttp (NOT httpx — httpx was removed).
│                         # CAN run on Cloud Run.
├── ui/
│   ├── __init__.py
│   ├── ui_theme.py       # Light/dark color tokens.
│   ├── ui_draw.py        # Canvas rendering — orb, agent rail, transcript, reasoning.
│   ├── ui_context.py     # Right panel — About You pills, Documents, history.
│   └── ui_animations.py  # Waveform, pulse, gradient, typing animations.
├── assets/
│   └── icons/
│       ├── frontend.png.png
│       ├── opensight_icon.png
│       └── opensight_icon_final.svg
├── server.py             # FastAPI WebSocket server. The brain.
│                         # Receives voice input, routes to agents, returns responses.
│                         # Deployed to Google Cloud Run at:
│                         # https://opensight-backend-348346331222.us-east1.run.app
│                         # NOTE: browser agents (shopping, research, calendar) fail
│                         # on Cloud Run — they need a local display for Playwright.
│                         # For full demo, run server locally (ws://127.0.0.1:8080/ws).
├── desktop_app.py        # Tkinter UI. Wake word listener, orb animation.
│                         # Connects to server over WebSocket.
│                         # Registers Win32 HWND via FindWindowW (not winfo_id).
├── audio_engine.py       # Deepgram STT + ElevenLabs TTS + wake word loop.
│                         # ElevenLabs uses elevenlabs 2.x SDK syntax (.stream() not .convert()).
│                         # TTS playback requires mpv installed and in PATH.
│                         # Endpointing set to 2500ms to avoid cutting off long phrases.
│                         # MIC_DEVICE_INDEX env var overrides default mic if needed.
├── memory.py             # SessionMemory dataclass. Persists across agents and turns.
│                         # Saves to opensight_memory.json after every turn.
├── browser_manager.py    # Tracks all open Chromium windows.
│                         # snapshot_chromium_hwnds() must be called BEFORE p.chromium.launch()
│                         # so _find_chromium_hwnd() can detect the new window by diff.
├── agent.py              # WebSocket bridge between desktop_app and server.
│                         # Sends queries, receives responses, updates UI state.
├── app_state.py          # Shared runtime state object passed everywhere.
│                         # Reads OPENSIGHT_WS_URL from env (falls back to localhost).
├── Dockerfile            # Cloud Run deployment. Runs uvicorn server only.
│                         # Does NOT include desktop_app, audio_engine, ui/ — server only.
├── .dockerignore         # Excludes secrets and desktop-only files from Docker image.
├── requirements.txt      # All pinned dependencies.
│                         # Must include: elevenlabs>=1.0.0, aiohttp>=3.9.0
├── DEMO.md               # Step-by-step demo script and reset commands.
├── README.md             # Public-facing project documentation.
└── CLAUDE.md             # This file.
```

---

## Files Never Committed (create locally)

These are gitignored — every developer creates them manually:

| File | How to get it |
|---|---|
| `.env` | Copy `.env.example`, fill in all keys |
| `credentials.json` | Download from Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID download |
| `token.json` | Auto-generated on first calendar query (browser OAuth flow) |
| `run_local.py` | Create manually — see Per-Developer Config below |

---

## Environment Variables (.env)

```
GEMINI_API_KEY=                    # aistudio.google.com/apikey
DEEPGRAM_API_KEY=                  # console.deepgram.com
ELEVENLABS_API_KEY=                # elevenlabs.io → Profile → API Keys
ELEVENLABS_VOICE_ID=onwK4e9ZLuTAKqWW03F9
GOOGLE_SEARCH_API_KEY=             # console.cloud.google.com → APIs → Custom Search
GOOGLE_SEARCH_CX=                  # programmablesearchengine.google.com
SERPAPI_KEY=                       # serpapi.com/dashboard
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
DEMO_MODE=false
WAKE_WORD_ENABLED=true
OPENSIGHT_WS_URL=ws://127.0.0.1:8080/ws   # change to wss://...run.app/ws for Cloud Run
MIC_DEVICE_INDEX=                  # optional — set to override default mic (see below)
USER_TIMEZONE=America/New_York     # optional — calendar agent timezone
```

---

## Per-Developer Local Config

Some settings differ per machine and must never be committed. Use `run_local.py` for these — it is gitignored.

**Create `run_local.py` in project root:**

```python
import os
import sounddevice as sd

# ── Machine-specific overrides ──────────────────────────────────────────────

# mpv PATH — required for ElevenLabs TTS playback on Windows.
# Find your mpv path with: Get-ChildItem "C:\Users\<you>\scoop\apps\mpv" -Recurse -Filter "mpv.exe"
os.environ["PATH"] += r";C:\Users\YOUR_USERNAME\scoop\apps\mpv\0.41.0"

# Mic device index — only needed if your default mic isn't being picked up.
# Find your index with: python -c "import sounddevice as sd; print(sd.query_devices())"
# sd.default.device[0] = 1  # uncomment and set your index if needed

# ── Start the app ───────────────────────────────────────────────────────────
exec(open("desktop_app.py").read())
```

Run with: `python run_local.py`

---

## Setup From Scratch

```powershell
# 1. Clone and enter project
git clone <repo-url>
cd GDG2

# 2. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Enable Windows long paths (required — run PowerShell as Administrator)
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browser
playwright install chromium

# 6. Install mpv for TTS audio playback (Windows)
# Option A — Scoop (recommended, handles dependencies automatically):
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex
scoop bucket add extras
scoop install extras/mpv
# Find install path: Get-ChildItem "$env:USERPROFILE\scoop\apps\mpv" -Recurse -Filter "mpv.exe"
# Add that path to run_local.py (see Per-Developer Config above)

# 7. Create .env (copy from .env.example and fill in all keys)

# 8. Place credentials.json in project root (download from Google Cloud Console)

# 9. Create run_local.py (see Per-Developer Config above)

# 10. Install gcloud CLI for Cloud Run work
# Download from: cloud.google.com/sdk/docs/install
# After install, add to PATH if not recognized:
$env:PATH += ";C:\Users\$env:USERNAME\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
gcloud auth login
gcloud config set project gdg-search-492804
```

---

## Running the App

### Local development (full functionality including browser agents)

```powershell
# Terminal 1 — backend server
uvicorn server:app --host 127.0.0.1 --port 8080

# Terminal 2 — desktop app
python run_local.py
```

Make sure `OPENSIGHT_WS_URL=ws://127.0.0.1:8080/ws` in `.env`.

### Fresh start (wipe memory before demo)

```powershell
Remove-Item shopping_memory.json, conversation_history.json, opensight_memory.json -ErrorAction SilentlyContinue
uvicorn server:app --host 127.0.0.1 --port 8080
```

### Demo flow (four queries)

1. *"Find me research on omega-3 and brain health"* → Research agent, Scholar opens
2. *"Find me a supplement for that under $30"* → Cross-agent handoff, Amazon opens
3. *"Open the first one"* → Product page opens, ingredients scraped
4. *"What are the ingredients"* → Answered from live page, not web search

---

## Cloud Run Deployment

### Current deployment

- **URL:** `https://opensight-backend-348346331222.us-east1.run.app`
- **Project:** `gdg-search-492804`
- **Region:** `us-east1`
- **Min instances:** 1 (always warm, no cold start)

### Critical limitation (current state)

Shopping, research, and calendar agents use Playwright to open browser windows — this requires a local display and **cannot run on Cloud Run**. Only the general agent and routing layer work fully on Cloud Run.

**For demo right now:** Run server locally. Cloud Run exists for the scalability narrative — "the AI orchestration layer is deployed on Google Cloud Run and can serve any number of users simultaneously."

### Redeploy command

```powershell
gcloud run deploy opensight-backend `
  --source . `
  --platform managed `
  --region us-east1 `
  --allow-unauthenticated `
  --min-instances 1 `
  --memory 1Gi `
  --timeout 300 `
  --set-env-vars "GEMINI_API_KEY=xxx,DEEPGRAM_API_KEY=xxx,ELEVENLABS_API_KEY=xxx,GOOGLE_SEARCH_API_KEY=xxx,GOOGLE_SEARCH_CX=xxx,SERPAPI_KEY=xxx"
```

---

## Planned Refactor — Browser Agents to Desktop Client (Option B)

**Status:** Planned. Do not start until after org demos (week of May 19). Target completion before mentorship sessions May 26.

### Why

Currently the server runs Playwright browser automation alongside AI logic. This breaks on Cloud Run (no display) and makes the Cloud Run story partially fake. The refactor splits responsibilities cleanly:

| Layer | Current | After refactor |
|---|---|---|
| Cloud Run (server.py) | Everything including Playwright | Routing, Gemini, memory, general, calendar API only |
| Desktop client | UI + audio only | UI + audio + all Playwright browser execution |

After the refactor, Cloud Run actually works end to end for everything except intentional local browser automation. The pitch becomes: "The AI orchestration layer runs on Google Cloud Run and scales to any number of users. Each client handles its own browser automation locally — we're not spinning up headless browsers on our servers for every user, which would be expensive and slower. This is the production-ready architecture."

### What changes

**New WebSocket message types needed:**

Server → client (new):
```json
{"type": "browser_action", "agent": "SHOPPING", "query": "omega-3 supplement under $30"}
{"type": "browser_action", "agent": "RESEARCH", "query": "omega-3 brain health"}
```

Client → server (new):
```json
{"type": "browser_result", "agent": "SHOPPING", "data": {"results": [...], "scraped": {...}}}
{"type": "browser_result", "agent": "RESEARCH", "data": {"papers": [...], "product_hint": "..."}}
```

**Files that change:**
- `server.py` — detect SHOPPING/RESEARCH intent, send `browser_action` instead of calling agent directly, wait for `browser_result`, then synthesize response
- `agent.py` — handle `browser_action` messages, dispatch to local browser executor, send back `browser_result`
- `agents/shopping.py` — split into server-side (response synthesis) and client-side (Playwright execution)
- `agents/research.py` — same split
- `desktop_app.py` — receive and dispatch browser actions

**Files that do NOT change:**
- `agents/router.py` — routing logic unchanged
- `agents/general.py` — already Cloud Run compatible
- `agents/calendar.py` — Calendar API calls stay server-side; only the browser open (calendar.google.com) moves to client
- `memory.py` — unchanged
- `browser_manager.py` — unchanged
- `audio_engine.py` — unchanged
- All UI files — unchanged

### Cross-agent memory during refactor

The trickiest part. Currently `research.py` stores `product_hint` in `memory.entities` on the server. After the refactor, the browser result comes back from the client — the server needs to extract `product_hint` from the returned paper data and store it in memory before routing the next query. Do not lose this or the research→shopping handoff breaks.

### How to execute with Claude Code

See the Claude Code prompt at the bottom of this file. Always commit clean before starting. Use `git reset --hard` if something goes wrong.

---

## Architecture Decisions

**Why two terminals?**
`server.py` is the FastAPI backend. `desktop_app.py` is the Tkinter UI. They communicate over WebSocket (`ws://127.0.0.1:8080/ws`). Keeping them separate allows the backend to be deployed to Cloud Run independently.

**Why aiohttp instead of httpx in general.py?**
httpx caused Pylance import errors and install issues. aiohttp is the standard async HTTP client and is fully compatible with the FastAPI async event loop.

**Why run_in_executor for Gemini calls?**
`client.models.generate_content()` is synchronous. Calling it directly inside an async function blocks the entire FastAPI event loop — every other WebSocket connection stalls until Gemini responds. Wrapping in `loop.run_in_executor()` runs it in a thread pool.

**Why snapshot_chromium_hwnds() before launch?**
The original `_find_chromium_hwnd()` took a snapshot after `p.chromium.launch()` had already returned — meaning the new window was already in the snapshot and was never detected as "new." The fix: call `browser_manager.snapshot_chromium_hwnds()` before launching, pass it as `seen_before` to `_find_chromium_hwnd()`.

**Why FindWindowW instead of winfo_id() for HWND?**
`winfo_id()` returns Tkinter's internal widget handle on Windows, not the Win32 HWND that `SetForegroundWindow` expects. `FindWindowW(None, "OpenSight")` looks up the window by its title string and reliably returns the correct Win32 HWND.

**Why endpointing=2500ms?**
Deepgram was cutting off long phrases like "find me a supplement for that under $30" mid-sentence — it detected a tiny pause between "that" and "under" as end of speech at 1200ms. 2500ms gives enough room for natural speech rhythm.

---

## Known Issues and Status

| Issue | Status | File |
|---|---|---|
| Browser agents fail on Cloud Run (no display) | Known — run locally for demo | shopping.py, research.py, calendar.py |
| Amazon scraping breaks if layout changes | Known — no fix yet | shopping.py |
| Cross-agent memory resets on Cloud Run (stateless) | Known — use local server for demo | server.py |
| Calendar agent needs credentials.json + token.json | Not on Cloud Run yet | calendar.py |
| Win32 focus may fail on some machines | Known — HWND lookup by title not guaranteed | browser_manager.py, desktop_app.py |

---

## Fixes Already Applied (do not revert)

- `router.py` — `generate_with_fallback` is async via `run_in_executor`. Research followup check moved above shopping followup check. `RESEARCH_EXPLICIT_PATTERN` guard added.
- `calendar.py` — macOS Chrome path removed, replaced with Playwright. `strftime("%-I")` replaced with `.lstrip("0")`. Google API calls wrapped in `run_in_executor`. `close_active_browser()` stub added for server.py import compatibility.
- `research.py` — `_is_followup` uses keyword matching instead of word count. "Open it" dead-end fixed. Mutable default arg fixed.
- `shopping.py` — `get_event_loop()` replaced with `get_running_loop()`. Supplement skip list added.
- `general.py` — httpx replaced with aiohttp. Default search key fixed. Mutable default arg fixed.
- `browser_manager.py` — `snapshot_chromium_hwnds()` public helper added. `_find_chromium_hwnd` accepts `seen_before` parameter.
- `desktop_app.py` — `_register_hwnd` uses `FindWindowW` instead of `winfo_id()`.
- `audio_engine.py` — `_should_fire_wake` unused param removed. TTS suppression increased to 1.2s. ElevenLabs updated to 2.x SDK syntax (`.stream()` not `.convert()`). Endpointing increased to 2500ms.
- `server.py` — duplicate `import sys` removed. `WindowsProactorEventLoopPolicy` replaced with `DefaultEventLoopPolicy`. Dead browser imports removed. Pre-routing `_is_followup` block removed — all routing owned by `plan_intent`.
- `memory.py` — double-indentation in `save()` fixed.
- `requirements.txt` — `elevenlabs>=1.0.0` and `aiohttp>=3.9.0` added.

---

## Troubleshooting
**Cloud Run build fails — "no such file or directory: Dockerfile"**
The file must be named exactly `Dockerfile` (capital D, lowercase f).
Windows sometimes saves it as `DockerFile`. Fix with:
Rename-Item DockerFile Dockerfile
**gcloud not recognized**
```powershell
$env:PATH += ";C:\Users\$env:USERNAME\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
```

**mpv not found (ElevenLabs TTS fails)**
Find your Scoop mpv path and add to `run_local.py`:
```powershell
Get-ChildItem "$env:USERPROFILE\scoop\apps\mpv" -Recurse -Filter "mpv.exe" | Select FullName
```

**Mic not picked up**
```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```
Find your mic's index number, set `sd.default.device[0] = <index>` in `run_local.py`.

**pip install fails (long path error)**
Run PowerShell as Administrator:
```powershell
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**Gemini 403 PERMISSION_DENIED — API key leaked**
Get a new key at aistudio.google.com/apikey. Do not commit `.env`.

**Deepgram 401 Unauthorized**
Generate a new key at console.deepgram.com — old key is invalid.

**"I couldn't find anything" on Amazon**
If running via Cloud Run (`OPENSIGHT_WS_URL=wss://...`), switch to local server. Playwright cannot run on Cloud Run.

**Deepgram cuts off mid-sentence**
Increase endpointing in `audio_engine.py` line with `endpointing=2500`. Do not go above 3000ms or responses feel sluggish.

---

## Claude Code Prompt — Browser Agent Refactor

Use this exact prompt when starting the Option B refactor with Claude Code. Read the Planned Refactor section above first.

```
Read CLAUDE.md in full before touching any file. It contains the full project context, architecture decisions, all fixes already applied, and the complete refactor plan. Do not revert any of the fixes listed in the "Fixes Already Applied" section.

I need to refactor OpenSight so browser automation moves from the server to the desktop client. The goal is to make the FastAPI backend fully deployable on Google Cloud Run — currently it fails because Playwright can't open browser windows on Cloud Run (no display).

CURRENT ARCHITECTURE:
- server.py receives a voice query, calls plan_intent() to route it, then calls run_shopping_agent() or run_research_agent() directly — these use Playwright to open Chrome on screen
- desktop_app.py only handles UI and audio — it sends queries and receives text responses

TARGET ARCHITECTURE:
- server.py detects SHOPPING or RESEARCH intent, sends a browser_action JSON message to the desktop client, waits for a browser_result response, then uses the returned data to synthesize the voice response via Gemini
- desktop_app.py (via agent.py) receives browser_action messages, runs the Playwright logic locally, and sends browser_result back to the server

NEW MESSAGE TYPES:
Server → client:
{"type": "browser_action", "agent": "SHOPPING", "query": "omega-3 supplement under $30"}
{"type": "browser_action", "agent": "RESEARCH", "query": "omega-3 brain health"}

Client → server:
{"type": "browser_result", "agent": "SHOPPING", "data": {"results": [...], "scraped": {...}}}
{"type": "browser_result", "agent": "RESEARCH", "data": {"papers": [...], "product_hint": "..."}}

CRITICAL CONSTRAINTS:
1. Do not break cross-agent memory. Research stores product_hint in memory.entities — after the refactor the server must extract product_hint from the browser_result data and store it before routing the next query. The research→shopping handoff ("find me a supplement for that") must still work.
2. Do not change router.py routing logic — it already handles research-before-shopping priority correctly.
3. Do not change general.py, memory.py, browser_manager.py, audio_engine.py, or any ui/ files.
4. agents/shopping.py and agents/research.py should be split: keep server-side synthesis logic in the agents folder, move Playwright execution to a new desktop_browser.py module that agent.py imports.
5. The existing WebSocket message types (status, research_status, response) must still work — only add new types, don't remove old ones.
6. Maintain backward compatibility: if OPENSIGHT_WS_URL points to localhost, the app should still work in local mode with the old architecture as a fallback.

BEFORE WRITING ANY CODE:
1. Read every file in the project
2. Map out every place Playwright is called
3. Map out every existing WebSocket message type in server.py and agent.py
4. Write out the complete list of changes you plan to make to each file
5. Wait for approval before making any changes

Start with the mapping and plan only.
```
