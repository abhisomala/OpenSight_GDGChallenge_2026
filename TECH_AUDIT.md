# OpenSight Technical Audit

Read-only audit of the working tree. Each finding cites file + symbol (no line
numbers). "NOT FOUND" means the thing was searched for and does not exist; it is
never inferred.

---

## 1. Voice input (speech-to-text)

**Verdict: Partial / split per client. Gemini Live: NOT FOUND (absent).**

- **Desktop client:** `audio_engine.py` → `_deepgram_listen` and `_wake_word_listen`
  open a WebSocket to `wss://api.deepgram.com/v1/listen` with `model=nova-2`.
  Speech-to-text is **Deepgram Nova-2**, streamed live from the local microphone
  (`sounddevice.InputStream`). The same module also runs the wake-word loop on Deepgram.
- **Android client:** `mobile/lib/speech_service.dart` → `SttSpeechService` uses the
  Flutter `speech_to_text` plugin (on-device OS recognizer), final-result-only. It is
  **not** Deepgram and not Gemini. Dependency confirmed in `mobile/pubspec.yaml`
  (`speech_to_text: 7.4.0`).
- **Gemini Live / live audio streaming to Gemini:** a repo-wide search for
  `Gemini Live`, `gemini-live`, `live audio`, `live.connect`, `BidiGenerate`, and
  `streaming` returned **no matches**. There is no Gemini Live audio path anywhere.
  All Gemini usage is text-in/text-out `generate_content` (see §3).

---

## 2. Text-to-speech (spoken output)

**Verdict: Partial. Google Cloud TTS is the real desktop path (with OS fallback);
Android uses on-device TTS. ElevenLabs: present only as dead config/comments, NOT used.**

- **Desktop:** `audio_engine.py` → `speak_text` calls `google.cloud.texttospeech`
  (`TextToSpeechClient.synthesize_speech`) when `GOOGLE_TTS_CREDENTIALS` points at a
  valid creds file, voice from `GOOGLE_TTS_VOICE`. So **Google Cloud Text-to-Speech is
  the actual primary path.** On any failure it falls back to OS TTS (macOS `say`,
  Windows `System.Speech`, Linux `espeak`).
- **Android:** `mobile/lib/tts_service.dart` → `FlutterTtsService` uses the `flutter_tts`
  plugin (on-device engine). Not Google Cloud TTS.
- **ElevenLabs:** referenced but **never called**. A stale comment in
  `audio_engine.py` (`voice_worker`) mentions "ElevenLabs streams audio…"; `.env` and
  `.env.example` carry `ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID` (commented out in
  `.env`); `requirements.txt` still lists `elevenlabs>=1.0.0`; and
  `tests/test_ui_layout.py::test_elevenlabs_not_in_raw_svcs` actively asserts ElevenLabs
  must **not** appear in the UI. No import or runtime call to ElevenLabs exists.

---

## 3. LLM routing (which Gemini models, where)

**Verdict: Yes, Gemini Flash family only. Gemini 2.5 Pro fallback: NOT FOUND.**

- `agents/router.py` → `MODELS` / `_FALLBACK_CHAIN` / `PRIMARY_MODEL` define the chain.
  `PRIMARY_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")`. The fallback chain is:
  `"gemini-2.5-flash"`, `"gemini-2.5-flash-lite"`, `"gemini-3.5-flash"`,
  `"gemini-3.1-flash-lite"` (the last two are commented as forward-compat 404s today).
- The only call site is `agents/router.py` → `generate_with_fallback`, which iterates
  `MODELS` calling `client.models.generate_content(model=m, ...)`. Every agent
  (`router`, `research`, `general`, `calendar`, and the multi-step combine in
  `server.py`) routes text generation through this one function.
- **There is no `gemini-*-pro` anywhere in the chain or codebase.** Routing is
  Flash/Flash-Lite only; there is no Pro fallback path.

---

## 4. Vertex AI vs developer key

**Verdict: Partial — both code paths exist; selected at runtime by env var. Default
(no env) is the developer API key path.**

- `agents/router.py` → `_make_client` branches on
  `GOOGLE_GENAI_USE_VERTEXAI`. When truthy it returns
  `genai.Client(vertexai=True, project=GOOGLE_CLOUD_PROJECT, location=GOOGLE_CLOUD_LOCATION)`
  — Vertex AI via Application Default Credentials (ADC), no API key. Otherwise it returns
  `genai.Client(api_key=os.getenv("GEMINI_API_KEY"))` — the Gemini **developer API key**.
- Credential loading: `GEMINI_API_KEY` is read from the environment (`.env` via
  `load_dotenv()`). Vertex uses ADC (from `gcloud auth application-default login` per
  `SETUP.md`), not an explicit service-account JSON file in code — there is **no**
  `service_account.Credentials.from_service_account_file(...)` call for Gemini anywhere.
- In practice the committed `.env.example` and the working-tree `.env` both set
  `GOOGLE_GENAI_USE_VERTEXAI=true`, so the configured deployment uses Vertex+ADC. But the
  code default with no env set is the developer-key branch, and a live `GEMINI_API_KEY` is
  present in `.env` (see §12). README's "service account" wording is imprecise — the Vertex
  path here is ADC, not a service-account-file credential. See CLAIMS AT RISK.

---

## 5. Deployment

**Verdict: Partial — strong evidence of a Cloud Run deployment, but both clients
default to localhost / 10.0.2.2.**

- **Evidence of cloud hosting:**
  - `DockerFile` (committed): `python:3.11-slim`, installs `requirements.txt`, `EXPOSE 8080`,
    `CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]`. It also strips
    secrets at build (`RUN rm -f .env token.json credentials.json ...`).
  - `server.py` (module top-level): decodes `GOOGLE_TTS_CREDENTIALS_B64` into
    `tts_credentials.json` "when running on Cloud Run", and a comment notes "Cloud Run
    reuses the process across sessions."
  - `run_tests.py` → `WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"`
    — a concrete Cloud Run backend URL. **Note:** `run_tests.py` is **untracked** (not
    committed), so this hardcoded remote URL is not in version control.
- **Client defaults (what they actually connect to):**
  - Desktop: `app_state.py` → `AppState.__init__` sets
    `self.agent_ws_url = os.getenv("OPENSIGHT_WS_URL", "ws://127.0.0.1:8080/ws")`. Working-tree
    `.env` also pins `OPENSIGHT_WS_URL=ws://127.0.0.1:8080/ws`. Default = **localhost**.
  - Android: `mobile/lib/config.dart` → `engineUrl = 'ws://10.0.2.2:8080/ws'` (emulator alias
    for host loopback). Default = **localhost via emulator**.
- Neither committed client points at the Cloud Run URL by default; the remote URL appears
  only in the untracked test script.

---

## 6. De-hardcoding (research → shopping handoff)

**Verdict: Yes — the product hint is generated by a Gemini call, not a hardcoded
keyword/regex product table.**

- The handoff logic lives in `agents/router.py` → `plan_intent`, in the
  "cross-agent: research → shopping handoff" block: when there is recent research context
  and `SHOPPING_INTENT_PATTERN` matches, it reads `memory.entities["product_hint"]` and
  builds the Amazon query as `f"{product_hint}{price_clause}"`.
- The `product_hint` itself is produced by `agents/research.py` → `_extract_product_hint`,
  which calls `generate_with_fallback` (Gemini) asking for a "2-4 word Amazon search phrase",
  stored via `synthesize_research_response`. There is a small **stopword-stripping fallback**
  inside `_extract_product_hint` only if the LLM returns empty/too-verbose/raises — not a
  topic→product mapping table.
- There is **no** large hardcoded topic→product keyword table. (The regexes in `router.py`
  — `SHOPPING_INTENT_PATTERN` etc. — only *detect intent/context*; they do not map topics to
  specific products.)

---

## 7. Fast-path (local follow-up handling without Gemini)

**Verdict: Yes — multiple local short-circuits.**

- **Routing short-circuits (no Gemini routing call):** `agents/router.py` → `plan_intent`
  returns an intent step from pure regex before reaching the Gemini planner, via
  `PRODUCT_CONTEXT_PATTERN`, `GENERAL_KNOWLEDGE_PATTERN`, `RESEARCH_FOLLOWUP_PATTERN`,
  `SHOPPING_FOLLOWUP_PATTERN`, `SHOPPING_INTENT_PATTERN`, and `PRONOUN_RESEARCH_PATTERN`.
  These match follow-up cues like "open/first/second", "tell me more", "find a supplement
  for that", "research on that".
- **Fully Gemini-free responses:** `agents/shopping.py` → `_handle_followup_query`,
  `get_followup_product_url`, `get_followup_product_title`, `_extract_option_index`
  answer "repeat", ordinal selection, and open-intent follow-ups with no model call;
  `server.py`'s SHOPPING follow-up branch and RESEARCH open-intent branch
  (`get_open_intent`) dispatch `browser_action` / canned text without Gemini.
- **Input gating:** `server.py` → `_is_garbled`, `_ACTIONABLE_SHORT`, `_SINGLE_WORD_GENERAL`
  reject/short-circuit junk and single-word utterances before routing. (Note: the
  single-word "fast-path" in `websocket_endpoint` still calls `run_general_agent`, which
  *does* hit Gemini — it only bypasses the *routing* call, not all Gemini.)

---

## 8. Firebase auth on the WebSocket

**Verdict: Partial — implemented, behind a feature flag that defaults to OFF; not
enforced by default. Android sends a token; desktop does not.**

- **Server-side verification:** `server.py` → `websocket_endpoint` (with helper
  `_ensure_firebase`). When enabled, it reads the first frame, requires
  `{"type":"auth","token":...}`, and calls `firebase_admin.auth.verify_id_token`; on
  failure it closes with code `4001`.
- **Feature flag + default:** `server.py` → `REQUIRE_AUTH = os.getenv("REQUIRE_AUTH","").lower() == "true"`.
  Default is **False** (empty env). `.env.example` ships `REQUIRE_AUTH=` (blank) with the
  comment "leave unset for demo (default off)". **So by default the server enforces no
  auth and accepts any connection.**
- **Android client:** `mobile/lib/config.dart` sets `requireAuth = true`;
  `mobile/lib/main.dart` initializes Firebase and `signInAnonymously`; and
  `mobile/lib/engine_client.dart` → `EngineClient.sendQuery` sends
  `{"type":"auth","token":...}` (from `_firebaseIdToken`) as the first frame when
  `requireAuth` is true. So the Android client **does** sign in and send a token.
- **Desktop client:** `agent.py` → `_query_agent_response_async` connects and immediately
  sends `{"text": user_text}` with **no auth frame**. The desktop client sends **no token**;
  if `REQUIRE_AUTH=true` were set server-side, the desktop client would be rejected (4001).
- **Net default behavior:** nothing is enforced. The two ends are also mismatched
  (Android `requireAuth=true` vs server `REQUIRE_AUTH` default false), and the desktop
  client can never satisfy auth as written.

---

## 9. Session memory (cross-agent / cross-reconnect)

**Verdict: Yes — `SessionMemory` dataclass with JSON-file persistence plus a
process-global instance. `last_general_topic` exists.**

- Class: `memory.py` → `SessionMemory` (dataclass). Fields: `history`, `preferences`,
  `last_results`, `entities`, `last_agent`, `last_query`. Persistence: `save()` writes
  `opensight_memory.json`; `load()` rehydrates it. `context_for_prompt()` injects a compact
  context string into every agent prompt.
- Cross-agent: a single instance is shared across all agents within a turn (passed as
  `memory=` into router/research/shopping/general/calendar). Cross-reconnect survival has
  **two** mechanisms: (a) `server.py` holds it as a module-global
  `_session_memory = SessionMemory.load()` that outlives any single WebSocket on a warm
  process, and (b) it is written to disk via `_session_memory.save()` on every turn.
- `last_general_topic`: set in `server.py` → `websocket_endpoint` GENERAL branch
  (`_session_memory.entities["last_general_topic"] = topic_words`) and consumed in
  `agents/router.py` → `plan_intent` (PRONOUN_RESEARCH_PATTERN block) to resolve
  "find research on that". It is stored inside the `entities` dict, which `save()`
  serializes, so it survives the per-utterance reconnect both in-process (global) and on
  disk. (Note: on reconnect `server.py` deliberately pops `scraped_content` and
  `last_product` from entities, but **not** `last_general_topic`.)

---

## 10. Agent inventory

| File / entry symbol | External API(s) called | What it does (one sentence) |
|---|---|---|
| `agents/router.py` (`plan_intent`, `generate_with_fallback`, `_make_client`) | **Gemini** (Vertex AI or Gemini Developer API via `google-genai`) | Classifies each utterance into one or more agent steps and is the single shared Gemini text-generation entry point for all agents. |
| `agents/shopping.py` (`synthesize_shopping_response`, `run_shopping_agent`, `_handle_followup_query`) | **Amazon** (indirectly — scraping runs client-side in `desktop_browser.py` via Playwright; this module is pure server-side synthesis) | Turns Amazon search results into spoken responses and handles shopping follow-ups (ordinal pick, repeat, open) with no model call. |
| `agents/research.py` (`search_scholar`, `synthesize_research_response`, `_extract_product_hint`) | **SerpAPI** (`google_scholar` engine) + **Gemini** | Searches Google Scholar via SerpAPI, summarizes papers, and uses Gemini to extract a `product_hint` for the research→shopping handoff. |
| `agents/calendar.py` (`run_calendar_agent`, `get_calendar_service`) | **Google Calendar API** (OAuth) + **Gemini** + Playwright (opens calendar.google.com) | Parses natural-language requests with Gemini and creates/lists Google Calendar events via the authenticated API. |
| `agents/general.py` (`run_general_agent`, `_search_web`) | **Google Custom Search API** + **Gemini** | Answers general questions using scraped product-page data or Google Custom Search snippets, synthesized by Gemini. |
| `desktop_browser.py` (`dispatch`, `_scrape_product_details`) | **Amazon** (`amazon.com/s`, `/dp/`) via Playwright Chromium | Client-side browser automation that performs the actual Amazon search and live product-page scraping for the SHOPPING agent. |

(`audio_engine.py` also calls **Deepgram** for STT and **Google Cloud TTS** for output, but
is the voice pipeline, not an "agent".)

---

## 11. Cost / token metering

**Verdict: NOT FOUND.**

A repo-wide search for `usage_metadata`, `count_tokens`, `total_tokens`,
`prompt_token`, `token_count`, `cost`, and `billing` returned no matches. There is no
token counting, no cost logging, and no per-query metering anywhere. The only Gemini-side
control is model fallback on quota/timeout in `agents/router.py` → `generate_with_fallback`.

---

## 12. Secrets in the working tree

**Verdict: Yes — live secrets are present in the working tree. Most are gitignored
(not committed); a couple of Firebase client config files are committed.**

Filenames only (contents not reproduced):

- **Present in the working tree but gitignored (NOT committed):**
  - `.env` — contains live `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`, `GOOGLE_SEARCH_API_KEY`,
    `SERPAPI_KEY` (and a commented-out ElevenLabs key).
  - `credentials.json` — Google OAuth client secrets (Calendar).
  - `token.json` — generated Google OAuth token.
  - `tts_credentials.json` — Google Cloud TTS service-account credentials.
  - (`.gitignore` covers all four; `git status --ignored` lists them as ignored.)
- **Committed / tracked in version control:**
  - `mobile/android/app/google-services.json` — Firebase Android config (contains a Firebase
    `current_key` / API key; client-side config, lower-sensitivity but still a key).
  - `mobile/lib/firebase_options.dart` — generated Firebase config (contains `apiKey` strings
    per platform; client-side config).

No service-account JSON for Gemini/Vertex is committed (Vertex uses ADC). The build
`DockerFile` explicitly deletes `.env`, `token.json`, and `credentials.json` from the image.

---

## CLAIMS AT RISK

Places where the code does not (fully) support a claim a README/marketing doc makes:

1. **STT provider is universal "Deepgram Nova-2."** `README.md` Architecture diagram and Tech
   Stack list voice input as "Deepgram Nova-2 real-time STT." True for the **desktop** client
   (`audio_engine.py`), but the **Android** client uses the on-device `speech_to_text` plugin
   (`mobile/lib/speech_service.dart`) — no Deepgram. The diagram implies one STT for all entry.

2. **TTS provider is "Google Cloud Text-to-Speech."** True on **desktop**
   (`audio_engine.py::speak_text`, with a silent OS fallback if creds are missing), but the
   **Android** client speaks via on-device `flutter_tts` (`mobile/lib/tts_service.dart`), not
   Google Cloud TTS. The README architecture routes all agents into a single "Google Cloud
   Text-to-Speech" box.

3. **Auth gates the backend ("verifies a Firebase ID token before accepting a connection").**
   `server.py` enforces this only when `REQUIRE_AUTH=true`, and the flag **defaults to OFF**
   (`.env.example` ships it blank with "default off"). By default the WebSocket accepts any
   connection with no token. README states gating as if always-on.

4. **Desktop client identity / "per-user" auth.** README says access "is gated by per-user
   identity." The **desktop** client (`agent.py`) sends no auth frame at all and would be
   rejected if auth were enabled — only the Android client sends a token. README does
   acknowledge desktop auth is "on the near-term roadmap," so this is partially hedged.

5. **"Vertex AI … via a service account."** README/Tech-Stack say Gemini is "called
   server-side via a service account." The code path (`router.py::_make_client`) uses Vertex
   via **ADC** (no service-account file in code), and the **default** branch with no env set
   is actually the **developer API key** (`GEMINI_API_KEY`), for which a live key exists in
   `.env`. So "service account" is imprecise and a keyless-Vertex deployment is configuration-
   dependent, not guaranteed by code.

6. **"No client holds the Gemini key."** Architecturally true for the shipped clients (they
   talk only to `/ws`), but a live `GEMINI_API_KEY` is present in the working-tree `.env`, and
   the default (non-Vertex) code path would use exactly that key — so the "keyless" guarantee
   depends on `GOOGLE_GENAI_USE_VERTEXAI=true` being set.

7. **"Cloud-hosted on Google Cloud" backend.** Supported by `DockerFile`, the Cloud Run creds
   handling in `server.py`, and a Cloud Run URL — but that URL lives only in the **untracked**
   `run_tests.py`; both committed clients default to `localhost` / `10.0.2.2`. There is no
   committed deploy script, Cloud Run YAML, or client config pointing at the hosted backend.

8. **Gemini Live.** Not claimed in `README.md`, and correctly so — there is **no** Gemini Live
   or live-audio-to-Gemini code anywhere in the repo. (Flagged here per the audit's explicit
   request: any future "Gemini Live" claim would be unsupported.)
