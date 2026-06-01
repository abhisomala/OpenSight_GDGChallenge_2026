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
| LLM | Gemini 2.5 Flash on **Vertex AI** (project `gdg-search-492804`, region `us-central1`) via `google-genai` SDK with `vertexai=True`. Primary set via `GEMINI_MODEL` env; fallback chain in router.py. AI Studio API key path preserved for backward compat — toggle with `GOOGLE_GENAI_USE_VERTEXAI`. |
| Agent orchestration | Python, custom multi-agent loop |
| Browser automation | Playwright (Chromium) — runs on desktop client (shopping/research), server-side only for calendar |
| Voice output | Google Cloud TTS (primary, WAV via PowerShell SoundPlayer), falls back to Windows SAPI / macOS say / Linux espeak |
| Backend | FastAPI + WebSockets |
| Desktop UI | Tkinter (custom LiquidGlass renderer) |
| Memory | JSON persistence + in-memory SessionMemory |
| Window management | Win32 ctypes (SetForegroundWindow) |
| Cloud | Google Cloud Run (backend deployed; shopping/research browser agents run on desktop client) |

---

## File Hierarchy

```
GDG2/
├── agents/
│   ├── __init__.py
│   ├── router.py         # Gemini intent classifier. Every query hits this first.
│   │                     # Routes to SHOPPING, RESEARCH, CALENDAR, GENERAL.
│   │                     # _make_client() picks Vertex AI vs AI Studio backend based on
│   │                     # GOOGLE_GENAI_USE_VERTEXAI. Single source of truth — every other
│   │                     # agent imports generate_with_fallback from here.
│   │                     # generate_with_fallback() wraps Gemini in run_in_executor so it
│   │                     # doesn't block the FastAPI event loop; fast-fails on 429 (~100ms)
│   │                     # and SDK retries disabled via _NO_RETRY_HTTP_OPTIONS.
│   │                     # MODELS = [GEMINI_MODEL env, then fallback chain] for resilience.
│   ├── shopping.py       # Server-side Amazon synthesis only (no Playwright).
│   │                     # synthesize_shopping_response() builds spoken response
│   │                     # from browser_result data received from desktop client.
│   │                     # run_shopping_agent() handles text-only follow-ups only.
│   │                     # Playwright execution is in desktop_browser.py.
│   ├── research.py       # Server-side Scholar logic only (no Playwright).
│   │                     # search_scholar() calls SerpAPI and returns papers.
│   │                     # synthesize_research_response() builds spoken response.
│   │                     # run_research_agent() handles text-based follow-ups only.
│   │                     # Playwright execution is in desktop_browser.py.
│   ├── calendar.py       # Google Calendar API — reads and creates events.
│   │                     # Opens calendar.google.com via Playwright (still server-side).
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
│                         # For SHOPPING/RESEARCH: sends browser_action to desktop client,
│                         # waits for browser_result (SHOPPING/SHOPPING_OPEN), or
│                         # fire-and-forget (RESEARCH/RESEARCH_OPEN).
│                         # Deployed to Google Cloud Run at:
│                         # https://opensight-backend-348346331222.us-east1.run.app
│                         # NOTE: calendar agent still uses Playwright on server —
│                         # fails on Cloud Run. For full demo, run server locally.
├── desktop_browser.py    # All Playwright browser execution for shopping and research.
│                         # Dispatched from agent.py when server sends browser_action.
│                         # run_amazon_search() — search + scrape results
│                         # open_product_page() — open product URL + scrape details
│                         # open_scholar_browser() — open Scholar URL
│                         # open_paper_window() — open individual paper URL
│                         # dispatch() — routes browser_action agent names to functions
│                         # All functions run synchronously via asyncio.to_thread().
├── desktop_app.py        # Tkinter UI. Wake word listener, orb animation.
│                         # Connects to server over WebSocket.
│                         # Clears memory files on startup for fresh context.
│                         # Registers Win32 HWND via FindWindowW (not winfo_id).
│                         # PyInstaller-aware resource path resolution.
│                         # Agent toggle UI (enable/disable agents per session).
├── audio_engine.py       # Deepgram STT + TTS + wake word loop.
│                         # TTS priority:
│                         #   1. Google Cloud TTS (if GOOGLE_TTS_CREDENTIALS is set)
│                         #      — writes WAV to temp file, plays via PowerShell SoundPlayer
│                         #   2. Windows: PowerShell System.Speech.Synthesis
│                         #      macOS: say -v Ava   Linux: espeak
│                         # ElevenLabs and mpv are NO LONGER USED.
│                         # Endpointing set to 3000ms (main STT loop).
│                         # Wake word endpointing is 300ms (separate Deepgram connection).
│                         # MIC_DEVICE_INDEX env var overrides default mic if needed.
├── memory.py             # SessionMemory dataclass. Persists across agents and turns.
│                         # Saves to opensight_memory.json after every turn.
├── browser_manager.py    # Tracks all open Chromium windows.
│                         # snapshot_chromium_hwnds() must be called BEFORE p.chromium.launch()
│                         # so _find_chromium_hwnd() can detect the new window by diff.
├── agent.py              # WebSocket bridge between desktop_app and server.
│                         # Sends queries, receives responses, updates UI state.
│                         # Handles browser_action messages: dispatches to desktop_browser,
│                         # returns browser_result to server.
│                         # SHOPPING/SHOPPING_OPEN: synchronous (server waits for result).
│                         # RESEARCH/RESEARCH_OPEN: fire-and-forget background task.
├── app_state.py          # Shared runtime state object passed everywhere.
│                         # Reads OPENSIGHT_WS_URL from env (falls back to localhost).
│                         # Holds 5-step reasoning chain state for UI visualization.
├── Dockerfile            # Cloud Run deployment. Runs uvicorn server only.
│                         # Does NOT include desktop_app, audio_engine, ui/ — server only.
├── .dockerignore         # Excludes secrets and desktop-only files from Docker image.
├── requirements.txt      # All pinned dependencies.
│                         # Includes: google-cloud-texttospeech>=2.16.0, aiohttp>=3.9.0,
│                         #           pillow==12.2.0, playwright==1.58.0
│                         # Note: elevenlabs>=1.0.0 is present but no longer used in code.
│                         # Note: httpx is present (used by serpapi indirectly).
├── DEMO.md               # Step-by-step demo script and reset commands.
├── README.md             # Public-facing project documentation.
└── CLAUDE.md             # This file.
```

---

## WebSocket Message Types

All messages are JSON. This is the complete current protocol between server and client.

**Server → Client:**

| type | Fields | When sent |
|---|---|---|
| `status` | `agent`, `state`, `detail` | Every routing step — client updates the agent rail UI |
| `research_status` | `text` | Progress updates during Scholar search |
| `response` | `text` | Final spoken response — client speaks this and ends the turn |
| `browser_action` | `agent`, `query` or `url` | Tells client to run a Playwright action |

**Client → Server:**

| type | Fields | When sent |
|---|---|---|
| (query) | `text` | User's spoken query |
| `browser_result` | `agent`, `data` | Playwright result from a browser_action |

**browser_action agents:**

| agent value | Server waits? | What client does |
|---|---|---|
| `SHOPPING` | Yes | `run_amazon_search(query)` — returns `{results, scraped}` |
| `SHOPPING_OPEN` | Yes | `open_product_page(url)` — returns `{scraped}` |
| `RESEARCH` | No | `open_scholar_browser(url)` — fire-and-forget |
| `RESEARCH_OPEN` | No | `open_paper_window(url)` — fire-and-forget |

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
GEMINI_API_KEY=                    # aistudio.google.com/apikey — used only when GOOGLE_GENAI_USE_VERTEXAI is not true
GEMINI_MODEL=gemini-2.5-flash      # optional — primary Gemini model (default gemini-2.5-flash, the working model on Vertex us-central1)
GOOGLE_GENAI_USE_VERTEXAI=true     # route Gemini calls through Vertex AI instead of the AI Studio Developer API
GOOGLE_CLOUD_PROJECT=gdg-search-492804   # Vertex AI project ID
GOOGLE_CLOUD_LOCATION=us-central1        # Vertex AI region
DEEPGRAM_API_KEY=                  # console.deepgram.com
GOOGLE_SEARCH_API_KEY=             # console.cloud.google.com → APIs → Custom Search
GOOGLE_SEARCH_CX=                  # programmablesearchengine.google.com
SERPAPI_KEY=                       # serpapi.com/dashboard
GOOGLE_APPLICATION_CREDENTIALS=credentials.json   # for Calendar OAuth
GOOGLE_TTS_CREDENTIALS=credentials.json           # for Google Cloud TTS (can be same file)
GOOGLE_TTS_VOICE=en-US-Journey-F                  # optional — default is en-US-Journey-F
GOOGLE_TTS_CREDENTIALS_B64=        # Cloud Run only — base64-encoded TTS credentials JSON
WAKE_WORD_ENABLED=true
OPENSIGHT_WS_URL=ws://127.0.0.1:8080/ws   # change to wss://...run.app/ws for Cloud Run
MIC_DEVICE_INDEX=                  # optional — set to override default mic (see below)
USER_TIMEZONE=America/New_York     # optional — calendar agent timezone
```

> **Note:** `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` are in `.env.example` but ElevenLabs is no longer used in the codebase. `DEMO_MODE` is no longer referenced in code.

---

## Per-Developer Local Config

Some settings differ per machine and must never be committed. Use `run_local.py` for these — it is gitignored.

**Create `run_local.py` in project root:**

```python
import os
import sounddevice as sd

# ── Machine-specific overrides ──────────────────────────────────────────────

# Mic device index — only needed if your default mic isn't being picked up.
# Find your index with: python -c "import sounddevice as sd; print(sd.query_devices())"
# sd.default.device[0] = 1  # uncomment and set your index if needed

# ── Start the app ───────────────────────────────────────────────────────────
exec(open("desktop_app.py").read())
```

Run with: `python run_local.py`

> **Note:** mpv is no longer required. TTS now uses Google Cloud TTS (WAV via PowerShell SoundPlayer) or the system fallback (Windows SAPI / macOS say / Linux espeak).

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

# 6. Create .env (copy from .env.example and fill in all keys)

# 7. Place credentials.json in project root (download from Google Cloud Console)

# 8. Create run_local.py (see Per-Developer Config above)

# 9. Install gcloud CLI for Cloud Run work
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

> **Note:** The desktop app also wipes these files automatically on startup.

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

### What works on Cloud Run (current state)

Shopping and research browser automation now run on the **desktop client** (via `desktop_browser.py`), not the server. Cloud Run handles routing, Gemini, memory, general, and the SerpAPI call for research.

**Remaining limitation:** The calendar agent still opens `calendar.google.com` via Playwright on the server — this still requires a local display and fails on Cloud Run.

**For demo right now:** Run server locally. Cloud Run exists for the scalability narrative — "the AI orchestration layer is deployed on Google Cloud Run and can serve any number of users simultaneously. Each client handles its own browser automation."

### Redeploy command

Vertex AI requires three new env vars and one IAM grant on the Cloud Run runtime
service account (`348346331222-compute@developer.gserviceaccount.com`):

```powershell
# One-time IAM grant so Cloud Run can call Vertex without an API key.
gcloud projects add-iam-policy-binding gdg-search-492804 `
  --member="serviceAccount:348346331222-compute@developer.gserviceaccount.com" `
  --role="roles/aiplatform.user"

# Deploy with Vertex env vars (GEMINI_API_KEY kept as backup for the AI Studio path).
# Do NOT set GOOGLE_APPLICATION_CREDENTIALS on Cloud Run — the runtime service account
# is auto-discovered via the metadata server, and setting that var would break Vertex ADC.
gcloud run deploy opensight-backend `
  --source . `
  --platform managed `
  --region us-east1 `
  --allow-unauthenticated `
  --min-instances 1 `
  --memory 1Gi `
  --timeout 300 `
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=gdg-search-492804,GOOGLE_CLOUD_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash,GEMINI_API_KEY=xxx,DEEPGRAM_API_KEY=xxx,GOOGLE_SEARCH_API_KEY=xxx,GOOGLE_SEARCH_CX=xxx,SERPAPI_KEY=xxx,GOOGLE_TTS_CREDENTIALS_B64=xxx"
```

---

## Completed Refactor — Browser Agents Moved to Desktop Client

**Status:** Complete. Browser automation for shopping and research now runs on the desktop client.

### What changed

| Layer | Before refactor | After refactor |
|---|---|---|
| Cloud Run (server.py) | Routing + Gemini + all Playwright | Routing + Gemini + memory + general + SerpAPI |
| Desktop client | UI + audio only | UI + audio + all shopping/research Playwright |
| Calendar | Server-side Playwright | Server-side Playwright (unchanged) |

### How it works now

1. Server detects SHOPPING intent → sends `browser_action {"agent": "SHOPPING", "query": "..."}` to desktop
2. `agent.py` receives `browser_action`, calls `desktop_browser.dispatch("SHOPPING", query=...)`
3. `desktop_browser.run_amazon_search()` opens Playwright Chromium, scrapes results
4. `agent.py` sends `browser_result {"agent": "SHOPPING", "data": {results, scraped}}` back to server
5. Server calls `synthesize_shopping_response(browser_data, ...)` and builds the spoken reply
6. Server sends `response` message to client

RESEARCH and RESEARCH_OPEN are fire-and-forget — server synthesizes the response from SerpAPI data before the browser opens, so the client doesn't block.

### Cross-agent memory

Research stores `product_hint` in `memory.entities` on the server after `synthesize_research_response()` runs. This happens server-side before any `browser_action` is sent, so the handoff is preserved.

---

## Architecture Decisions

**Why two terminals?**
`server.py` is the FastAPI backend. `desktop_app.py` is the Tkinter UI. They communicate over WebSocket (`ws://127.0.0.1:8080/ws`). Keeping them separate allows the backend to be deployed to Cloud Run independently.

**Why `desktop_browser.py`?**
Browser automation (Playwright) requires a local display and cannot run on Cloud Run. Moving it to the desktop client makes the server Cloud Run-compatible for shopping and research. The module is self-contained — it does not import from `agents/` — so it can run on the client without server dependencies.

**Why aiohttp instead of httpx in general.py?**
httpx caused Pylance import errors and install issues. aiohttp is the standard async HTTP client and is fully compatible with the FastAPI async event loop.

**Why run_in_executor for Gemini calls?**
`client.models.generate_content()` is synchronous. Calling it directly inside an async function blocks the entire FastAPI event loop — every other WebSocket connection stalls until Gemini responds. Wrapping in `loop.run_in_executor()` runs it in a thread pool.

**Why snapshot_chromium_hwnds() before launch?**
The original `_find_chromium_hwnd()` took a snapshot after `p.chromium.launch()` had already returned — meaning the new window was already in the snapshot and was never detected as "new." The fix: call `browser_manager.snapshot_chromium_hwnds()` before launching, pass it as `seen_before` to `_find_chromium_hwnd()`.

**Why FindWindowW instead of winfo_id() for HWND?**
`winfo_id()` returns Tkinter's internal widget handle on Windows, not the Win32 HWND that `SetForegroundWindow` expects. `FindWindowW(None, "OpenSight")` looks up the window by its title string and reliably returns the correct Win32 HWND.

**Why Google Cloud TTS instead of ElevenLabs?**
ElevenLabs + mpv required a separate binary in PATH and had streaming complexity. Google Cloud TTS writes a WAV file to a temp path and plays it via PowerShell `SoundPlayer`, which is simpler and doesn't require any extra install. When `GOOGLE_TTS_CREDENTIALS` is not set, the code falls back to Windows SAPI / macOS `say` / Linux `espeak`.

**Why endpointing=3000ms?**
Deepgram was cutting off long phrases mid-sentence. 3000ms gives enough room for natural speech rhythm. The wake word loop uses a separate Deepgram connection with 300ms endpointing so it stays snappy.

**Why SHOPPING browser_action is synchronous but RESEARCH is fire-and-forget?**
Shopping results must come back before the server can synthesize the response (it needs the product list and prices). Research synthesis happens entirely from SerpAPI data — the browser opening (Scholar page) is just a visual companion for the user, not input to the response. So RESEARCH doesn't need to block.

---

## Known Issues and Status

| Issue | Status | File |
|---|---|---|
| Calendar agent still uses Playwright on server (fails on Cloud Run) | Known — run locally for demo | calendar.py |
| Amazon scraping breaks if layout changes | Known — no fix yet | desktop_browser.py |
| Cross-agent memory resets on Cloud Run (stateless) | Known — use local server for demo | server.py |
| Calendar agent needs credentials.json + token.json | Not on Cloud Run yet | calendar.py |
| `GOOGLE_APPLICATION_CREDENTIALS=credentials.json` in .env conflicts with Vertex ADC locally — the file is an OAuth client config (calendar reads it directly via `InstalledAppFlow.from_client_secrets_file('credentials.json', …)`, not via the env var), but ADC misreads it as a malformed service account. Unset the env var locally when using Vertex — calendar still works. On Cloud Run, do not set this var (the runtime service account is auto-discovered via the metadata server). | Known — see Troubleshooting | .env, calendar.py |
| `gemini-3.5-flash` / `gemini-3.1-flash-lite` return 404 on Vertex us-central1 today | Known — kept in chain as forward-compat for when they GA in this region | router.py |
| Win32 focus may fail on some machines | Known — HWND lookup by title not guaranteed | browser_manager.py, desktop_app.py |
| elevenlabs in requirements.txt but not used in code | Stale dependency — safe to ignore | requirements.txt |

---

## Fixes Already Applied (do not revert)

- `router.py` — `generate_with_fallback` is async via `run_in_executor`. Research followup check moved above shopping followup check. `RESEARCH_EXPLICIT_PATTERN` guard added. Primary model reads from `GEMINI_MODEL` env (default `gemini-2.5-flash`); current chain order is `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.1-flash-lite` — the 3.x IDs are kept as forward-compat no-ops since they 404 on Vertex us-central1 today. Preview aliases and retired 2.0/1.5 IDs are gone.
- `router.py` — Vertex AI migration. Added `_make_client()` helper as single source of truth: when `GOOGLE_GENAI_USE_VERTEXAI=true`, constructs `genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)`; otherwise falls back to `api_key=GEMINI_API_KEY` so the AI Studio path still works. Same google-genai SDK; only the backend changes. Eliminates the AI Studio 429 quota issue that was causing fallthroughs.
- `router.py` — Quota-error fast-fail. `_NO_RETRY_HTTP_OPTIONS` (`HttpRetryOptions(attempts=1)`) disables the SDK's built-in tenacity backoff that was making 429s consume the full 15s timeout. `_is_quota_error()` detects `errors.ClientError` code 429 / status `RESOURCE_EXHAUSTED` and advances to the next model in ~100ms instead of ~15s. 15s outer timeout preserved for genuine slowness.
- `calendar.py` — macOS Chrome path removed, replaced with Playwright. `strftime("%-I")` replaced with `.lstrip("0")`. Google API calls wrapped in `run_in_executor`. `close_active_browser()` stub added for server.py import compatibility.
- `research.py` — `_is_followup` uses keyword matching instead of word count. "Open it" dead-end fixed. Mutable default arg fixed. Playwright removed — execution moved to `desktop_browser.py`. `search_scholar()` / `synthesize_research_response()` split for server+client protocol. `get_open_intent()` added for server.py. Paper deduplication by title added.
- `shopping.py` — `get_event_loop()` replaced with `get_running_loop()`. Supplement skip list added. Playwright removed — execution moved to `desktop_browser.py`. `synthesize_shopping_response()` / `run_shopping_agent()` split for server+client protocol. `get_followup_product_url()` / `get_followup_product_title()` helpers added.
- `general.py` — httpx replaced with aiohttp. Default search key fixed. Mutable default arg fixed. `_build_search_query` falls back to full question instead of hardcoded "ingredients".
- `browser_manager.py` — `snapshot_chromium_hwnds()` public helper added. `_find_chromium_hwnd` accepts `seen_before` parameter.
- `desktop_app.py` — `_register_hwnd` uses `FindWindowW` instead of `winfo_id()`. Memory files cleared on startup. PyInstaller resource path support added (`_resource_path`, `sys._MEIPASS`). Agent toggle UI added.
- `audio_engine.py` — ElevenLabs and mpv removed. TTS now uses Google Cloud TTS (primary) via `GOOGLE_TTS_CREDENTIALS` → WAV temp file → PowerShell SoundPlayer, with Windows SAPI / macOS say / Linux espeak fallback. Endpointing increased to 3000ms. Wake word endpointing is 300ms (separate connection). `_should_fire_wake` unused param removed.
- `server.py` — duplicate `import sys` removed. `WindowsProactorEventLoopPolicy` replaced with `DefaultEventLoopPolicy`. Dead browser imports removed. Pre-routing `_is_followup` block removed — all routing owned by `plan_intent`. `browser_action` / `browser_result` protocol added. `_wait_for_browser_result()` helper added. `GOOGLE_TTS_CREDENTIALS_B64` env var decoded on startup for Cloud Run TTS. Session state reset on each WebSocket connection.
- `agent.py` — `browser_action` handler added. `desktop_browser.dispatch()` called via `asyncio.to_thread()`. SHOPPING/SHOPPING_OPEN are synchronous (server waits); RESEARCH/RESEARCH_OPEN are background tasks.
- `desktop_browser.py` — New file. All Playwright execution for shopping and research. `run_amazon_search()`, `open_product_page()`, `open_scholar_browser()`, `open_paper_window()`, `dispatch()`.
- `memory.py` — double-indentation in `save()` fixed.
- `requirements.txt` — `google-cloud-texttospeech>=2.16.0`, `aiohttp>=3.9.0`, `pillow==12.2.0` added.

---

## Troubleshooting

**Cloud Run build fails — "no such file or directory: Dockerfile"**
The file must be named exactly `Dockerfile` (capital D, lowercase f).
Windows sometimes saves it as `DockerFile`. Fix with:
```powershell
Rename-Item DockerFile Dockerfile
```

**gcloud not recognized**
```powershell
$env:PATH += ";C:\Users\$env:USERNAME\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin"
```

**Google TTS not working (no audio or robotic fallback)**
Set `GOOGLE_TTS_CREDENTIALS` in `.env` to the path of your Google Cloud credentials JSON. The file must have Text-to-Speech API access enabled in the Cloud Console. Without this, the app falls back to Windows SAPI (robotic voice).

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
If running via Cloud Run (`OPENSIGHT_WS_URL=wss://...`), the desktop client still opens the browser locally — this should work. If it doesn't, check that `desktop_browser.py` is present and that Playwright Chromium is installed (`playwright install chromium`).

**Deepgram cuts off mid-sentence**
Increase endpointing in `audio_engine.py` in `_deepgram_listen` (currently `endpointing=3000`). Do not go above 4000ms or responses feel sluggish. Do not change the wake word loop endpointing (300ms) — that one must stay snappy.

**Calendar fails on Cloud Run**
Calendar still uses Playwright server-side. Run server locally for calendar functionality.

---

## Claude Code Prompt — Calendar Browser Refactor (Next Step)

If the calendar browser open needs to move to the desktop client (same pattern as shopping/research), use this prompt:

```
Read CLAUDE.md in full before touching any file. The shopping and research browser refactor (Option B) is already complete — desktop_browser.py exists and all their Playwright runs on the desktop client via browser_action/browser_result messages.

The remaining Playwright on the server is in calendar.py: _launch_calendar_browser() opens calendar.google.com in a thread. This needs to move to the desktop client using the same browser_action pattern already in place.

What to do:
1. In desktop_browser.py, add open_calendar_browser(url) following the same pattern as open_scholar_browser().
2. In dispatch(), add a "CALENDAR" case that calls open_calendar_browser().
3. In calendar.py, remove _launch_calendar_browser() and the threading.Thread call. Instead, the server should send: {"type": "browser_action", "agent": "CALENDAR", "url": "https://calendar.google.com"} after completing the API work, fire-and-forget.
4. In server.py, after run_calendar_agent() returns, send the CALENDAR browser_action (fire-and-forget — no need to wait for browser_result).
5. In agent.py, the CALENDAR agent should be handled as a background task (same as RESEARCH).

Do not change routing logic, memory, or API call logic in calendar.py. Only move the browser open.
```
