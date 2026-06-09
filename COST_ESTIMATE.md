# OpenSight — API Cost Estimate (per query, end to end)

Read-only estimate derived from the source. It traces one spoken query through the
system, counts the external API calls and their size, and prices them. Every number
is an estimate from prompt templates and typical responses in the code — **there is no
token metering anywhere in the repo** (`TECH_AUDIT.md` §11 confirms: no `usage_metadata`,
`count_tokens`, or cost logging exists), so all token counts are inferred, not measured.

> ⚠️ **Prices must be verified.** The per-unit prices in the constants block below are
> from general public-pricing memory (≈ Jan 2026) and **must be checked against current
> published pricing** before being used for anything real. They are isolated as named
> constants so they can be updated in one place.

---

## 0. Price constants (VERIFY ALL OF THESE)

```text
# Gemini 2.5 Flash (PRIMARY_MODEL = "gemini-2.5-flash", agents/router.py)
GEMINI_FLASH_INPUT_PER_MTOK   = $0.30    # USD per 1,000,000 input tokens   — VERIFY
GEMINI_FLASH_OUTPUT_PER_MTOK  = $2.50    # USD per 1,000,000 output tokens  — VERIFY
# (Fallback gemini-2.5-flash-lite is cheaper, ~$0.10 / $0.40. The forward-compat
#  3.5 / 3.1 models in the chain 404 today per code comments, so they never bill.)

# Deepgram Nova-2, streaming (audio_engine.py, model=nova-2)
DEEPGRAM_NOVA2_PER_MIN        = $0.0059  # USD per minute of streamed audio  — VERIFY

# Google Cloud Text-to-Speech (audio_engine.py speak_text, voice en-US-Journey-F)
GOOGLE_TTS_PER_MCHARS         = $16.00   # USD per 1,000,000 characters      — VERIFY + see note
# NOTE: en-US-Journey-F is a PREMIUM voice. TTS price depends entirely on voice tier:
#   Standard ≈ $4/M, WaveNet/Neural2 ≈ $16/M, Studio/Journey ≈ up to $160/M.
#   $16 is a mid estimate; the real figure for Journey-F could be ~10x higher. VERIFY.

# SerpAPI (agents/research.py, engine=google_scholar)
SERPAPI_PER_SEARCH            = $0.015   # USD per search (~$75 / 5,000 plan)  — VERIFY

# Google Custom Search JSON API (agents/general.py _search_web)
GOOGLE_CSE_PER_1000           = $5.00    # USD per 1,000 queries (free 100/day) — VERIFY
```

---

## 1. Path of a single spoken query

| Stage | Where (file → symbol) | External call |
|---|---|---|
| Speech-to-text | `audio_engine.py` → `_deepgram_listen` (and `_wake_word_listen` for the wake word) | **Deepgram Nova-2** streaming WebSocket (`wss://api.deepgram.com/v1/listen?model=nova-2`). Desktop only. |
| Transport | desktop `agent.py` → `_query_agent_response_async` sends `{"text": …}` to `/ws` | none (local WS) |
| Gate / junk filter | `server.py` → `websocket_endpoint`, `_is_garbled`, `_ACTIONABLE_SHORT`, `_SINGLE_WORD_GENERAL` | none |
| Preference extraction | `agents/router.py` → `plan_intent` → `extract_preferences` | **Gemini** (1 call, only if ≥ 4 words and the query reaches the LLM planner) |
| Routing / planning | `agents/router.py` → `plan_intent` → `generate_with_fallback` | **Gemini** (1 call) |
| Agent execution | one of: | |
| · GENERAL | `agents/general.py` → `run_general_agent` → `_search_web` then `generate_with_fallback` | **Google Custom Search** (1) + **Gemini** (1) |
| · RESEARCH (new) | `agents/research.py` → `search_scholar` then `synthesize_research_response` → `_extract_product_hint` | **SerpAPI** (1) + **Gemini** (1, the product-hint call) |
| · SHOPPING (new) | `agents/shopping.py` → `synthesize_shopping_response`; the actual Amazon search/scrape runs **client-side** in `desktop_browser.py` (Playwright) | **none paid** (Amazon scraped via Playwright; no metered API) |
| · CALENDAR | `agents/calendar.py` → `run_calendar_agent` (Gemini parse) → Google Calendar API | **Gemini** (1) + Google Calendar API (free quota) |
| Multi-step combine | `server.py` → `generate_with_fallback` | **Gemini** (1, only when a query produced > 1 step) |
| Text-to-speech | `audio_engine.py` → `speak_text` → `texttospeech.TextToSpeechClient.synthesize_speech` | **Google Cloud TTS**. Desktop only. |

**Client split (important for who pays):** the Android client (`mobile/lib/speech_service.dart`,
`mobile/lib/tts_service.dart`) uses **on-device** STT and TTS — so Deepgram and Google Cloud
TTS cost **$0 on mobile**. Only the **desktop** client incurs STT/TTS API cost. Gemini /
Custom Search / SerpAPI run server-side and bill for **both** clients.

---

## 2. One typical fully-routed query

I use a single-step **GENERAL** question with web search (the most common fully-routed path)
as the canonical case, then note how RESEARCH / CALENDAR / SHOPPING differ.

### Gemini calls (3 for a GENERAL query)

| # | Call (symbol) | Input tokens (est.) | Output tokens (est.) |
|---|---|---|---|
| 1 | `extract_preferences` prompt + query | ~100 (range 90–150) | ~30 |
| 2 | Planner: `SYSTEM_PROMPT` (~475 tok) + conversation history (up to 10 turns) + `memory.context_for_prompt()` + user msg | ~1,000 (range 600–1,500) | ~50 (small JSON) |
| 3 | GENERAL agent: `SYSTEM_PROMPT` (~115 tok) + memory ctx + history + 5 search snippets (~265 tok) + question | ~900 (range 600–1,200) | ~50 (2–3 sentences) |
| | **Total Gemini** | **~2,000 input** | **~130 output** |

Why three: `extract_preferences` and the planner are *both* Gemini calls inside `plan_intent`
(router.py lines ~347 and ~362), then the agent makes a third. The planner prompt is the
largest because it concatenates `SYSTEM_PROMPT` + the full `conversation_history` (server keeps
the last 10 turns) **and** `memory.context_for_prompt()` (which itself re-includes the last 6
turns + capped agent results) — there is deliberate redundancy there.

Variants (same 1–2 routing calls, different agent call):
- **RESEARCH (new search):** calls 1–2 as above, plus `_extract_product_hint` (~145 in / ~5 out — output is a 2–4 word phrase). `_build_response` is **not** an LLM call. So ~3 Gemini calls, but the 3rd is tiny.
- **CALENDAR:** calls 1–2, plus the parse prompt (~150–300 in / ~30 out JSON). ~3 Gemini calls.
- **SHOPPING (new search):** only calls 1–2 (**2 Gemini calls**); synthesis is pure Python, scraping is client-side. Lowest Gemini cost.
- **Cross-agent RESEARCH→SHOPPING or any 2-step plan:** add 1 more Gemini call (the combine prompt in `server.py`, ~120 in / ~40 out).

### Non-Gemini external calls (per fully-routed query)

| Service | Calls | Size |
|---|---|---|
| Deepgram Nova-2 STT | 1 stream | ~5 s of audio for a typical spoken query (**see caveat A** — billing is by connection time, not utterance length) |
| Google Cloud TTS | 1 | response text length, ~200 chars typical for 2–3 spoken sentences |
| Google Custom Search | **1** (GENERAL only) | `num=5` results, single API call |
| SerpAPI | **1** (RESEARCH only) | `num=5` Scholar results, single API call |

---

## 3. Fast-path follow-up query (local pattern match, skips Gemini)

This is the pure local short-circuit in `plan_intent` (e.g. "open the first one",
"repeat", "tell me more") — `SHOPPING_FOLLOWUP_PATTERN` / `RESEARCH_FOLLOWUP_PATTERN` /
`PRODUCT_CONTEXT_PATTERN` return a step **before** reaching the Gemini planner, and
`server.py` answers it with `get_followup_product_url` / `_handle_followup_query` /
`get_open_intent` — **no model call**.

**Calls avoided vs. a fully-routed query:**
- ❌ `extract_preferences` (Gemini) — short-circuit returns before it
- ❌ planner `generate_with_fallback` (Gemini)
- ❌ the agent's Gemini call (shopping/research followups are pure Python)
- ❌ Google Custom Search / SerpAPI

**Calls still made:**
- ✅ Deepgram STT (~3 s — "open the first one")
- ✅ Google Cloud TTS (short reply, e.g. "Opening the … now." ≈ 25 chars)
- (a SHOPPING_OPEN / RESEARCH_OPEN `browser_action` runs Playwright client-side — no paid API)

So a fast-path query makes **0 Gemini calls, 0 search calls** — only desktop STT + TTS.

> **Not the same as the "single-word fast-path"** in `server.py` (`websocket_endpoint`,
> "yes"/"ok"/"stop"…). That one skips the planner and `extract_preferences` but still calls
> `run_general_agent`, which **does** hit Gemini once (and may do 1 Custom Search). That path
> costs ~1 Gemini call, not zero. The estimate below is for the true Gemini-free follow-up.

---

## 4. Cost estimate

Token math uses the constants in §0. (input tok / 1e6 × INPUT_PER_MTOK) + (output tok / 1e6 × OUTPUT_PER_MTOK).

### Per fully-routed query — GENERAL (canonical)

| Component | Quantity | Cost |
|---|---|---|
| Gemini input | 2,000 tok | $0.00060 |
| Gemini output | 130 tok | $0.00033 |
| Deepgram STT | 5 s = 0.083 min | $0.00049 |
| Google Cloud TTS | 200 chars | $0.00320 |
| Google Custom Search | 1 query | $0.00500 |
| **Total** | | **≈ $0.0096 (~1.0¢)** |

Cost is dominated by **Custom Search ($0.005)** and **TTS ($0.0032)**, *not* Gemini (~$0.001).

### Per fully-routed query — RESEARCH variant

Replace Custom Search with SerpAPI; Gemini ~3 small calls; same STT/TTS.

| Component | Cost |
|---|---|
| Gemini (~3 calls, incl. tiny hint call) | ~$0.0009 |
| Deepgram STT (5 s) | $0.00049 |
| Google Cloud TTS (200 chars) | $0.00320 |
| SerpAPI | $0.01500 |
| **Total** | **≈ $0.0196 (~2.0¢)** |

SerpAPI dominates. SHOPPING (new search) is the cheapest fully-routed path (~$0.0046:
2 Gemini calls + STT + TTS, no paid search) and CALENDAR is similar to GENERAL minus the
search (~$0.0046).

### Per fast-path follow-up query

| Component | Quantity | Cost |
|---|---|---|
| Deepgram STT | 3 s = 0.05 min | $0.00030 |
| Google Cloud TTS | ~25 chars | $0.0000004 |
| **Total** | | **≈ $0.0003 (~0.03¢)** |

≈ **30× cheaper** than a fully-routed GENERAL query; essentially just STT.

### Per 1,000 queries

| Scenario | Cost / 1,000 |
|---|---|
| All fully-routed GENERAL | ~$9.6 |
| All fully-routed RESEARCH | ~$19.6 |
| All fast-path follow-ups | ~$0.30 |
| **Blended** (50% GENERAL, 25% RESEARCH, 25% fast-path) — *assumption* | ~$0.50·9.6 + 0.25·19.6 + 0.25·0.3 ≈ **$9.8** |

### Per monthly active user (MAU)

**Assumption (stated): 20 queries / month / user.** Mix and client both matter:

| MAU scenario | Make-up | Cost / month |
|---|---|---|
| All 20 fully-routed GENERAL (desktop) | 20 × $0.0096 | **~$0.19** |
| Blended desktop (10 GENERAL, 5 RESEARCH, 5 fast-path) | $0.096 + $0.098 + $0.0015 | **~$0.20** |
| Mobile-only user (no Deepgram, no Cloud TTS) | same calls minus STT/TTS | **~$0.13** (search/Gemini only) |

**Rough headline: ~$0.15–0.25 per MAU per month** for the metered APIs as written — **but
see Caveat A, which can dwarf this.**

---

## 5. Assumptions and places the code gave no firm number

**Caveat A — Deepgram STT is the biggest unknown and could dominate everything.**
Deepgram is a **continuous streaming WebSocket**, not a per-utterance request. In
`_deepgram_listen` the mic streams to Deepgram the whole time it is open (only paused
while `state.is_speaking`). Billing is **per minute of streamed audio**, so the real cost
is the **connection's open duration**, not the ~5 s a user actually speaks. If the desktop
app holds the connection open, e.g., 10 min/day, that is ~300 min/month ≈ **$1.77/MAU** for
STT alone — far above the whole §4 MAU figure. I used "5 s spoken audio per utterance" only
to attribute STT to a single query; the true per-user STT cost depends on listening time the
code does not bound. **Additionally**, `_wake_word_listen` opens a **second** Nova-2 stream
for wake-word detection; if it runs concurrently with the main listen, STT cost ~doubles.
I could not determine from these two functions alone whether the two streams overlap or
alternate (the orchestration lives in the desktop app's session/token switching).

**Other assumptions and soft numbers:**

1. **Token counts are inferred, never measured.** No token metering exists (`TECH_AUDIT.md` §11). I used ~4 chars/token. Prompt sizes scale with conversation length: the planner prompt grows with up to 10 history turns + memory context, so 1,000 input tok is a mid estimate (range 600–1,500). Early-session queries are cheaper; long sessions cost more.

2. **`extract_preferences` fires conditionally.** Only when the query is ≥ 4 words *and* reaches the LLM planner (memory is always passed by the server). Shorter routed queries skip it → 2 Gemini calls instead of 3. I assumed it fires for the canonical case.

3. **TTS voice tier is unresolved.** `en-US-Journey-F` is a premium voice. The $16/M constant is a mid guess; Journey/Studio voices can be billed up to ~$160/M. If so, TTS jumps from $0.0032 to ~$0.032/query and would rival Custom Search as the top cost. **Verify the exact billing tier for Journey-F.**

4. **TTS character count = response length.** I used ~200 chars for a 2–3 sentence reply (the prompts cap responses at 2–3 sentences). Longer replies (e.g. RESEARCH "repeat" listing 3 options, or CALENDAR listing 5 events) can be 2–4× larger.

5. **Search result counts are fixed in code** (`num=5` for both Custom Search and SerpAPI), but **price per call is plan-dependent**: SerpAPI ranges roughly $0.01–$0.015/search by plan; Custom Search is free for the first 100/day then $5/1,000 (capped at 10k/day). I assumed paid pay-as-you-go with no free tier — if the free 100/day Custom Search quota covers usage, GENERAL queries get much cheaper.

6. **Gemini fallback chain assumed to hit the primary model.** Costs assume `gemini-2.5-flash` serves the request. On quota/timeout, `generate_with_fallback` retries `gemini-2.5-flash-lite` (cheaper) — that would lower cost. The 3.5/3.1 entries 404 today (per code comments) and never bill. Vertex vs. developer-key backend (`_make_client`) does not change token pricing materially here.

7. **Amazon shopping has no metered API cost.** The product search/scrape is client-side Playwright (`desktop_browser.py`); I counted $0 for it. Real-world cost there is compute/proxy/anti-bot, not an API line item — out of scope for this estimate.

8. **Calendar / Firebase auth costs ignored.** Google Calendar API is within free quota for this volume; Firebase `verify_id_token` (only when `REQUIRE_AUTH=true`, default off) is effectively free at this scale.

9. **Query-mix and MAU split are invented for illustration.** The 50/25/25 blend and the 20-queries/month figure (the latter given by the task) are assumptions, not derived from code. There is no usage/analytics data in the repo to ground a real mix.

10. **Multi-step (combine) frequency unknown.** The combine Gemini call only fires for >1-step plans (e.g. RESEARCH→SHOPPING). I treated single-step as typical; a workload heavy in cross-agent handoffs adds ~1 Gemini call per such query.
