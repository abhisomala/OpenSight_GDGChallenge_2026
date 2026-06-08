# OpenSight: Setup (Developers)

This is the developer build and configuration guide. End users do not need any of this: they download the standalone Windows executable, run it, and say "OpenSight." See the [README](README.md) for the project overview and [DEMO.md](DEMO.md) for the demo script.

---

## Prerequisites

- Python 3.11+
- Windows (Win32 focus management) or macOS (partial support)
- A microphone
- Google Cloud SDK (`gcloud`) for Vertex AI authentication

---

## Installation

```bash
git clone https://github.com/abhisomala/gdg2
cd gdg2
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

---

## Google Cloud and Firebase

- **Vertex AI:** authenticate with Application Default Credentials: `gcloud auth application-default login`. Gemini runs on Vertex AI, so no Gemini API key is required.
- **Firebase:** configure the Firebase project (Authentication and Firebase AI Logic) in the Firebase console. Model access is routed through Firebase, keyless on the client.
- **Google Cloud Text-to-Speech:** enable the API and provide service credentials.

---

## Environment variables

Create a `.env` file in the project root. Note there is no `GEMINI_API_KEY` (Vertex AI uses ADC and Firebase AI Logic handles client access) and no ElevenLabs key.

```
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true
DEEPGRAM_API_KEY=your_key_here
GOOGLE_SEARCH_API_KEY=your_key_here
GOOGLE_SEARCH_CX=your_cx_here
SERPAPI_KEY=your_key_here
```

For Google Calendar OAuth, download `credentials.json` from Google Cloud Console and place it in the project root. `token.json` is generated on first run.

---

## Running

Once installed and configured, see **[DEMO.md](DEMO.md)** for the exact commands to start the server and desktop app and walk through the demo.

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
│   ├── ui_animations.py   # Animation loops
│   └── ui_theme.py        # Dark/light color system
├── assets/
│   └── icons/
│       └── frontend.png   # UI screenshot for README
├── server.py              # FastAPI WebSocket server + session persistence
├── desktop_app.py         # Main entry point + wake word integration
├── memory.py              # SessionMemory + JSON persistence
├── audio_engine.py        # Deepgram STT + Google Cloud TTS + wake word loop
├── browser_manager.py     # Cross-agent browser lifecycle + Win32 focus control
├── app_state.py           # Shared UI + agent state
├── requirements.txt       # Pinned dependencies
└── DEMO.md                # Step-by-step demo script
```