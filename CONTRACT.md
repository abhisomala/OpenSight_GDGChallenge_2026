# OpenSight `/ws` WebSocket Contract

This document describes **exactly** how the existing OpenSight **desktop client**
talks to the FastAPI `/ws` endpoint, so a future Flutter voice client can mirror it.

It was extracted by reading the source only. Every fact below cites the file and
the function/area it came from. Where a message's *text content* is generated at
runtime (LLM output), that is called out; only the **structure/field names** are
guaranteed by the code, and an illustrative value is shown.

> Scope note: The `/ws` contract is **text-in / text-out only**. Speech-to-text and
> text-to-speech are *not* part of this contract; the desktop client does its own STT
> (Deepgram) and TTS (Google/OS voices) entirely outside `/ws` (`audio_engine.py`:
> `_deepgram_listen`, `speak_text`). A Flutter voice client must supply its own STT/TTS
> and send/receive plain text over `/ws`, exactly as the desktop client does.

---

## 1. Connection

### URL / pattern
- **Client side:** the URL comes from `AppState.agent_ws_url`
  (`app_state.py`, `AppState.__init__`). It is read from the env var
  `OPENSIGHT_WS_URL`, defaulting to:
  ```
  ws://127.0.0.1:8080/ws
  ```
- The connection is opened in `agent.py`, function `_query_agent_response_async`,
  via `websockets.connect(state.agent_ws_url, open_timeout=5, close_timeout=1)`.
- **Server side:** the endpoint is declared in `server.py` as
  `@app.websocket("/ws")` → `websocket_endpoint(ws)`. The server is served by
  `uvicorn server:app --host 0.0.0.0 --port 8080` (`Dockerfile`, `CMD` / `EXPOSE 8080`),
  which matches the client's default port `8080`.

### One connection per utterance (NOT persistent)
- **The client opens one WebSocket per user query (per utterance).**
  In `agent.py` `_query_agent_response_async`, the entire exchange lives inside a
  single `async with websockets.connect(...) as ws:` block: it sends one query,
  loops receiving messages until it gets a `response`, then `break`s and exits the
  `async with`, which **closes the socket**. The next utterance calls
  `query_agent_response` again (via `process_recognized_text`), opening a brand-new
  connection.
- This is corroborated on the server side by the comment in `websocket_endpoint`
  referring to "the new-WebSocket-per-utterance model" when explaining why it reloads
  shopping memory from disk on each reconnect.
  Note on the server: `websocket_endpoint` *does* contain a `while True:` loop that
  could service multiple messages on one socket, but the desktop client never uses
  it that way; it disconnects after the first `response`. A Flutter client mirroring
  the desktop behavior should likewise open one connection per utterance. (Keeping the
  socket open and sending multiple `{"text": ...}` frames would also be accepted by the
  server, but that is **not** the path the desktop client exercises; see Open questions.)

---

## 2. Message the client SENDS (user query)

A single JSON **text frame** with one field, `text`.

- **Sender:** `agent.py`, `_query_agent_response_async`:
  `await ws.send(json.dumps({"text": user_text}))`
- **Receiver:** `server.py`, `websocket_endpoint`:
  `message = json.loads(data); user_text = message.get("text", "")`

### Structure
```json
{ "text": "<the user's spoken query as a string>" }
```

### Real example
```json
{ "text": "find me wireless headphones under fifty dollars" }
```

That is the **only** message the client sends to start a query. (It may later send
`browser_result` frames (see §4), but those are replies to server requests, not
new queries.)

---

## 3. Messages the client RECEIVES

All server→client frames are JSON text frames with a `type` discriminator. The
client's receive loop (`agent.py`, `_query_agent_response_async`) handles exactly
these `type` values: `status`, `research_status`, `browser_action`, `response`.

The **spoken response text is NOT streamed in chunks.** There are no partial/final
response fragments. The final answer arrives as a single `response` message, which
is also the **end-of-response signal** (the client `break`s its loop on it). The
`status` and `research_status` messages are *progress indicators only*, not pieces
of the answer.

### 3a. `status`: progress / which agent is working
- **Sender:** `server.py`, `send_status(ws, agent, state, detail)` (also emitted
  inline in `websocket_endpoint`).
- **Handler:** `agent.py` `msg_type == "status"` branch → updates the UI agent
  indicator; if `agent == "SHOPPING"` and `state == "thinking"`, the client also
  speaks "Searching Amazon now." once.

Structure:
```json
{ "type": "status", "agent": "<AGENT>", "state": "<state>", "detail": "<label>" }
```
- `agent` is one of the routing labels: `"BRAIN"`, `"SHOPPING"`, `"CALENDAR"`,
  `"RESEARCH"`, `"GENERAL"`, or `"IDLE"` (see `AGENT_LABELS` in `server.py` and
  `normalize_agent` in `agent.py`).
- `detail` for working agents comes from `AGENT_LABELS` (e.g. `"searching Amazon"`,
  `"routing"`, `"thinking"`). For the idle signal `detail` is `""` (default arg).

Real examples (all emitted in `server.py`):
```json
{ "type": "status", "agent": "BRAIN", "state": "thinking", "detail": "routing" }
```
```json
{ "type": "status", "agent": "SHOPPING", "state": "thinking", "detail": "searching Amazon" }
```
```json
{ "type": "status", "agent": "IDLE", "state": "idle", "detail": "" }
```

### 3b. `research_status`: fine-grained research progress text
- **Sender:** `server.py`, the inner `_research_status(msg)` callback inside
  `websocket_endpoint` (driven by the research agent's `status_cb`).
- **Handler:** `agent.py` `msg_type == "research_status"` branch → forwarded to the
  UI's research status line via `status_cb`.

Structure:
```json
{ "type": "research_status", "text": "<progress string>" }
```

Real example (the exact text strings are produced by `agents/research.py`
`search_scholar`, e.g. its first `_status(...)` call):
```json
{ "type": "research_status", "text": "Building search query..." }
```

### 3c. `browser_action`: server asks the client to drive a browser
This is a **server→client request**. On the desktop it triggers Playwright browser
automation (`desktop_browser.dispatch`). There are two behaviors:

- **Synchronous (server waits):** `agent == "SHOPPING"` or `"SHOPPING_OPEN"`.
  The client must run the action and reply with a `browser_result` (see §4); the
  server blocks on `_wait_for_browser_result` until it arrives (timeout 120s for
  `SHOPPING`, 30s for `SHOPPING_OPEN`).
- **Fire-and-forget (server does NOT wait):** `agent == "RESEARCH"` or
  `"RESEARCH_OPEN"`. The server has already produced / will send the `response`
  without waiting. The desktop client opens these in a background task
  (`agent.py` `_browser_action_background`).

Senders are all in `server.py` `websocket_endpoint`. Handler is the
`agent.py` `msg_type == "browser_action"` branch, which routes by `agent` name.

Structure (a `browser_action` carries **either** `query` **or** `url`):
```json
{ "type": "browser_action", "agent": "<AGENT>", "query": "<search query>" }
```
```json
{ "type": "browser_action", "agent": "<AGENT>", "url": "<page url>" }
```

Real examples:
```json
{ "type": "browser_action", "agent": "SHOPPING", "query": "wireless headphones under fifty dollars" }
```
```json
{ "type": "browser_action", "agent": "SHOPPING_OPEN", "url": "https://www.amazon.com/dp/B0XXXXXXX" }
```
```json
{ "type": "browser_action", "agent": "RESEARCH", "url": "https://scholar.google.com/scholar?q=..." }
```
```json
{ "type": "browser_action", "agent": "RESEARCH_OPEN", "url": "https://example.com/paper.pdf" }
```

### 3d. `response`: the final spoken answer (END-OF-RESPONSE signal)
- **Sender:** `server.py`, `websocket_endpoint`:
  `await ws.send_text(json.dumps({"type": "response", "text": final_response}))`
  (also used for the "didn't catch that" and single-word fast paths).
- **Handler:** `agent.py` `msg_type == "response"` branch → stores
  `final_response` and `break`s the receive loop, ending the exchange. After this
  the client closes the socket.

Structure:
```json
{ "type": "response", "text": "<the spoken answer>" }
```
- `text` is **dynamic** (LLM-generated at runtime); only the shape is fixed.

Real example (structure is exact; the `text` value is illustrative since it is
produced by the agents at runtime):
```json
{ "type": "response", "text": "I found a few options. The top pick is a pair of wireless headphones for $39.99." }
```

Exactly one `response` is sent per query, and it is always the last message of the
exchange. There is no separate "done"/"end" frame; `response` *is* the terminator.

---

## 4. Message the client SENDS in reply to `browser_action` (`browser_result`)

Not a query, but part of the contract: the client's answer to a `browser_action`.

- **Sender:** `agent.py`: `_query_agent_response_async` (synchronous SHOPPING /
  SHOPPING_OPEN) and `_browser_action_background` (fire-and-forget).
- **Receiver:** `server.py` `_wait_for_browser_result`, which matches on
  `msg.get("type") == "browser_result"` and `msg.get("agent") == <expected agent>`,
  then reads `msg.get("data", {})`.

Structure:
```json
{ "type": "browser_result", "agent": "<AGENT>", "data": { ... } }
```

For `agent == "SHOPPING"`, `data` is the dict returned by
`desktop_browser.run_amazon_search` (`desktop_browser.py`): a `results` list (up to
8 scraped Amazon items) plus an empty `scraped` map. Real shape:
```json
{
  "type": "browser_result",
  "agent": "SHOPPING",
  "data": {
    "results": [
      {
        "title": "Wireless Bluetooth Headphones Over Ear",
        "price": "$39.99",
        "price_val": 39.99,
        "url": "https://www.amazon.com/dp/B0XXXXXXX"
      }
    ],
    "scraped": {}
  }
}
```
(The server consumes this via `synthesize_shopping_response` in
`agents/shopping.py`.)

---

## 5. Error message shape

**There is no dedicated `{"type": "error"}` message in this protocol.** Errors are
delivered as ordinary `response` messages:

- **Server-side failure during handling:** `server.py` `websocket_endpoint` catches
  the exception, sets `final_response = f"Sorry, I ran into an issue: {str(e)}"`,
  and sends it as a normal `response`:
  ```json
  { "type": "response", "text": "Sorry, I ran into an issue: <error detail>" }
  ```
- **Unintelligible / too-short input:** before routing, the server replies with a
  fixed `response` and an idle status, then continues:
  ```json
  { "type": "response", "text": "I didn't catch that. Could you say that again?" }
  ```
  (followed by `{ "type": "status", "agent": "IDLE", "state": "idle", "detail": "" }`)

- **Client-side connection/transport failure:** handled locally, **no message is
  exchanged.** In `agent.py` `_query_agent_response_async`, any exception (e.g.
  connect timeout, socket error, the 180s `ws.recv()` timeout) is caught, the agent
  status is set to `IDLE`/`offline`, and the function returns `""` (empty string).
  `process_recognized_text` then retries the whole query once; if still empty, the
  desktop client speaks "Sorry, let me try that again." This behavior is purely
  client-side and is not driven by any server message.

So a Flutter client should treat an error as: a normal `response` frame whose `text`
begins with "Sorry, I ran into an issue:" (server error) or the fixed
"I didn't catch that…" string (rejected input), plus its own local handling for
transport-level failures.

---

## 6. Minimal happy-path sequence (GENERAL query)

```
client → server : { "text": "what's the capital of France" }
server → client : { "type": "status", "agent": "BRAIN", "state": "thinking", "detail": "routing" }
server → client : { "type": "status", "agent": "GENERAL", "state": "thinking", "detail": "thinking" }
server → client : { "type": "response", "text": "Paris is the capital of France." }
server → client : { "type": "status", "agent": "IDLE", "state": "idle", "detail": "" }   ← may arrive after `response`
client closes the socket (it stops reading after `response`)
```
Note: the client `break`s on `response`, so a trailing `status: idle` sent by the
server after `response` may simply be dropped when the socket closes. The end of the
exchange is defined by the `response` frame, not the idle status.

---

## Open questions

These are genuine ambiguities for the **Flutter mirror** (Phase 2), not gaps in the
documented desktop behavior above. Flagging per instructions rather than inventing:

1. **`browser_action` on a mobile client.** The synchronous `SHOPPING` /
   `SHOPPING_OPEN` actions require the client to perform **desktop Playwright browser
   automation** and return scraped `browser_result.data` (`desktop_browser.py`). A
   Flutter/Android client cannot drive a desktop browser. If a Flutter client never
   replies with `browser_result`, the server will **block** in
   `_wait_for_browser_result` (up to 120s for `SHOPPING`) before continuing. How
   should the Flutter client handle `browser_action`? Options to confirm with you:
   open URLs in the mobile browser / a WebView, send back an empty/synthetic
   `browser_result`, or have the backend gain a "mobile mode" that skips
   browser-dependent paths. **This needs your decision before Phase 2.**

2. **Connection lifetime choice.** The desktop client uses one-WebSocket-per-utterance.
   The server's loop technically supports a persistent connection with multiple
   `{"text": ...}` frames, but that path is untested by the existing client and the
   server reloads per-session state on each connect. Confirm whether the Flutter
   client should mirror one-per-utterance (recommended, matches what is proven) or
   attempt a persistent socket.

3. **Exact `research_status` text strings.** The `research_status.text` values are
   generated inside `agents/research.py` (`search_scholar`, `run_research_agent`) and
   are free-form progress strings. The *field shape* is certain; the full set of exact
   strings was not enumerated here. If the Flutter UI needs to match specific strings,
   confirm whether that matters (the desktop client just displays whatever arrives).
