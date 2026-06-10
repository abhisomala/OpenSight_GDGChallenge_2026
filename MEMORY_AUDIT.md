# OpenSight Memory Subsystem — Read-Only Audit

Audited 2026-06-10 against the working tree (branch `main`, post-Cloud-Run-default config
change, uncommitted). Citations are file + symbol. No source files were modified.

---

## 1. Memory class

**`SessionMemory` — still its current name — a `@dataclass` in `memory.py`.** It is the
single shared store the backend hands to every agent, instantiated once as the module-level
global `_session_memory` in `server.py`. It holds short-term conversational state plus
extracted long-term facts, capped aggressively (20 turns of history, 500-char agent results)
to limit prompt size.

Distinct state it stores (fields of `SessionMemory`):

| Field | Contents |
|---|---|
| `history` | Last 20 user/assistant turns, each tagged with role, agent, timestamp (`add_turn`) |
| `preferences` | Extracted long-term user facts — budget, allergies, diet (`update_preferences`) |
| `last_results` | Per-agent last output, capped at 500 chars, readable by all agents (`set_result`) |
| `entities` | Dict with default keys `topics`, `products`, `dates`, `people`, `constraints`, plus dynamically added keys: `product_hint`, `last_general_topic` (see §2). `scraped_content` and `last_product` are cleared on connect but have **no writer** in current code — vestigial. |
| `last_agent` | Name of the agent that last ran (`set_result`) |
| `last_query` | The user's last utterance (set directly in `server.py`, `websocket_endpoint`) |

Of the default entity keys, only `topics` is actually written today (`agents/router.py`
`extract_preferences`; `agents/research.py` `synthesize_research_response`). `products`,
`dates`, `people`, `constraints` are initialized but never populated anywhere.

Separate, **outside** `SessionMemory`: `server.py` also keeps `_shopping_memory` (dict,
`_load_shopping_memory`/`_save_shopping_memory`) and `_conversation_history` (list,
`_load_conversation_history`/`_save_conversation_history`) as parallel module-level stores
with their own JSON files. Memory is therefore three stores, not one.

## 2. Cross-agent handoff

Context flows through the shared `SessionMemory` instance that `server.py`
(`websocket_endpoint`) passes as the `memory=` argument to every agent, plus the router
reading it at intent-planning time. The keys that exist today:

- **`entities["product_hint"]`** (RESEARCH → SHOPPING) — **set** in `agents/research.py`
  `synthesize_research_response`, which calls `_extract_product_hint` (an LLM call over the
  found papers) and stores the result. **Read** in `agents/router.py` `plan_intent` (the
  research→shopping handoff branch builds the enriched shopping query from it, appending any
  price clause from the user's text) and in `_has_recent_research_context` (its presence
  counts as research context). **Cleared** in `server.py` `websocket_endpoint` after a
  SHOPPING turn completes, so research context doesn't bleed into post-shopping queries.
- **`entities["last_general_topic"]`** (GENERAL → RESEARCH) — **set** in `server.py`
  `websocket_endpoint` after a GENERAL turn (topic words from the query). **Read** in
  `agents/router.py` `plan_intent`, which substitutes it for pronouns ("that"/"it"/"this")
  in a follow-up research query.
- **`last_results` / `last_agent`** (any → any) — **set** by every agent via
  `SessionMemory.set_result` (`agents/shopping.py`, `research.py`, `calendar.py`,
  `general.py`). **Read** indirectly by every agent via `SessionMemory.context_for_prompt`,
  which injects "What {agent} agent found: …" into each agent's system prompt.
- **`preferences`** (router → all) — **set** in `agents/router.py` `extract_preferences`
  (LLM extraction of budget/allergies/diet, called from `plan_intent`). **Read** via
  `context_for_prompt` by all agents.

There is also a second, non-`SessionMemory` handoff: `plan_intent` enriches follow-up
queries with `_shopping_memory["last_results"][0]`'s title ("user is looking at …").

## 3. Persistence

**Plain JSON files in the server process's working directory — global, not per-user or
per-session.** Three files:

- `opensight_memory.json` — written by `SessionMemory.save` (called from `server.py`
  `websocket_endpoint` after each turn), loaded by `SessionMemory.load` at module import.
- `shopping_memory.json` — `server.py` `_save_shopping_memory` / `_load_shopping_memory`.
- `conversation_history.json` — `server.py` `_save_conversation_history` /
  `_load_conversation_history` (loaded at import; note: the save function exists and history
  is appended in-process, but persistence is via these module functions).

There is **no per-user keying anywhere**: no user id, no session id, no database. One set of
files per server process. `server.py` supports a `--fresh` flag that deletes all three files
at startup. On Cloud Run the container filesystem is ephemeral, so these files survive only
as long as the warm instance does — and are shared by **all** users hitting that instance.

## 4. Reconnect survival

**There is no session or user key — NOT FOUND.** Memory survives reconnects by virtue of
being module-level globals in the server process plus the JSON files, not by any reattachment
mechanism. On each new connection, `server.py` `websocket_endpoint` (a) re-reads
`shopping_memory.json` into `_shopping_memory` so shopping follow-ups survive the
client's one-WebSocket-per-utterance model, and (b) pops `scraped_content` / `last_product`
from `_session_memory.entities`. `_session_memory` itself simply persists in process memory
across connections. The code's own comment calls this a deliberate trade-off: it gives up
cross-session isolation, "acceptable for the single-user local demo." On Cloud Run this
means all clients share one memory on a warm instance, and memory resets on cold start.

## 5. Context panel

**Exists: `ui/ui_context.py`, class `ContextMixin`** (the "Context" tab in the desktop
Tkinter client; `ui/ui_draw.py` also reads memory for display). It is **read AND
partially editable**, with one big caveat:

- **Read:** `_draw_context_panel` calls `SessionMemory.load()` directly (reads
  `opensight_memory.json` from disk) and shows preferences (budget/allergy/diet pills),
  learned topics, last agent + last query, and recent conversation bubbles.
- **Remove:** `remove_learned_item` genuinely edits the store — it loads the JSON, removes
  the clicked pill (budget, allergy, diet, or topic), and calls `m.save()`. So removal is
  real, not display-only.
- **Add:** the "Documents" section (`_add_context_document_from_inputs`) only appends to
  `self.context_documents`, a UI-local list. It is **never written to `SessionMemory` and
  never sent to the backend** — the panel itself prints "Resets on app close." So user-added
  context does not reach the agents.
- **Caveat:** the panel reads the JSON file from the *client's* working directory. That only
  coincides with the backend's memory when the backend runs locally in the same directory.
  With the new default (Cloud Run backend), the server's `opensight_memory.json` lives in the
  container, so the desktop panel shows stale/empty local data and its removals edit a file
  the backend never reads.

## 6. Recent changes (git, memory-related files only)

`memory.py` itself is stable — last touched **2026-05-14** (`1351759` "updated agent
functionality & readme - removed bugs"); created 2026-04-14 (`60fd6d1`). The churn has been
in `server.py` and the agents:

| Commit | Date | Message | Files touched |
|---|---|---|---|
| `6aa593f` | 2026-06-07 | just cleaned up redundant code in server.py | server.py (1 deletion) |
| `89c7cb2` | 2026-06-04 | firebase auth firing, waiting on flutter for firebase ai | server.py (+33) |
| `68d1e09` | 2026-06-03 | changing logic flow, in progress | agents/research.py (−75/+30 net rewrite), server.py |
| `0eba2a1` | 2026-06-01 | implmented vertex ai & gemini live | server.py |
| `e9a3862` | 2026-06-01 | Migrate Gemini calls to Vertex AI… | agents/router.py |
| `eb1b216` | 2026-06-01 | gemini model upgrade | agents/router.py |
| `b92634b` | 2026-05-20 | memory fix | (memory-adjacent) |
| `f6a22f7` | 2026-05-17 | theoretically fixes stale memory issue | (memory-adjacent) |
| `cdb504b` | 2026-05-17 | made everything work for the desktop .exe … cross agent memory & functionality better | (broad) |

`ui/ui_context.py` last changed **2026-05-21** (`6e6cc03`, UI polish only — no behavior
change since 2026-04-19). The takeaway: the memory *class* hasn't changed in nearly a month,
but `server.py`'s connection-handling around it (auth, per-connect resets) and
`agents/research.py`'s handoff logic changed in the first week of June.

## 7. Claims check

| Claim | Verdict | Reason |
|---|---|---|
| "a shared session memory held in the backend, shared across all agents" | **MATCHES** | `_session_memory` in `server.py` is passed to every agent; all read it via `context_for_prompt`. (Minor nuance: shopping/conversation state live in two parallel stores beside it.) |
| "persists across WebSocket reconnects" | **PARTIAL** | True in effect (process globals + JSON reload in `websocket_endpoint`), but there is no session/user keying or reattachment — on Cloud Run it is one global memory per warm instance, lost on cold start. |
| "JSON persistence plus in-memory SessionMemory" | **MATCHES** | Exactly the mechanism: `SessionMemory.save`/`load` → `opensight_memory.json`, plus the two sibling JSON files. |
| "holds preferences, history, and learned context" | **MATCHES** | `preferences`, `history`, `entities`/`last_results` are all real and populated — though only `topics` of the five default entity lists is ever written. |
| "a product hint or last topic is stored for the cross-agent handoff" | **MATCHES** | `entities["product_hint"]` (research→shopping, set in `synthesize_research_response`, read in `plan_intent`) and `entities["last_general_topic"]` (general→research) both exist today. |
| "a context panel lets the user see and edit what the system has learned" | **PARTIAL** | `ContextMixin` shows learned state and can genuinely *remove* items (`remove_learned_item` saves to JSON), but user-*added* context (Documents) never reaches memory or the backend — and the panel reads the local JSON file, which no longer reflects backend memory now that the default backend is Cloud Run. |

## WHAT CHANGED / WHAT TO UPDATE

1. **"Persists across reconnects" needs a qualifier.** It persists via process globals and
   working-directory JSON, with no session/user id. After the switch to the Cloud Run
   default, the honest statement is: memory persists per server instance — shared across all
   users on a warm instance, reset on cold start. Don't claim per-user persistence; nothing
   is keyed by user (Firebase auth verifies a token but the id is never used for memory).
2. **The context panel is now disconnected from the default backend.** It reads/writes the
   *local* `opensight_memory.json`, which only mirrors backend memory when the server runs
   locally in the same directory. Any claim that the user can "see and edit what the system
   has learned" should be scoped to the local-backend configuration (or the panel should be
   reworked to query the backend).
3. **"Edit" overstates the Documents feature.** Removal of learned pills is real; added
   Documents are UI-only, never persisted, never sent to agents. Say "view and remove" unless
   the add path gets wired up.
4. **Entity coverage is narrower than the schema suggests.** Of `topics/products/dates/
   people/constraints`, only `topics` is written; `scraped_content` and `last_product` are
   cleared on connect but no longer written by anything — vestigial after the June 3
   `agents/research.py` rewrite (`68d1e09`). Docs should name only `topics`, `product_hint`,
   and `last_general_topic` as live learned context.
5. **Memory is three stores, not one.** `SessionMemory` plus `_shopping_memory`
   (`shopping_memory.json`) plus `_conversation_history` (`conversation_history.json`), each
   with separate persistence. If docs imply a single unified store, soften to "a shared
   session memory plus per-domain JSON stores."
