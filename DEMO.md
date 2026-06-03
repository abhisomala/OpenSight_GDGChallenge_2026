# OpenSight — Demo Script

> Scope: this is the local run used to walk through and record the demo. Production distribution is the packaged Windows `.exe` against the Google Cloud backend (see the README). The steps below run the system locally for a clean, controlled demo.

## Before you start

```bash
# Terminal 1
uvicorn server:app --host 127.0.0.1 --port 8080 --fresh

# Terminal 2
python desktop_app.py
```

Wait for both to print ready. Make sure your microphone is the default input device.

---

## The demo — say these four things in order

**1.** `"Find me research on omega-3 and brain health"`

> Google Scholar opens. OpenSight reads back two paper titles and stores a product hint in memory.

**2.** `"Can you find me a supplement for that under $30"`

> Scholar closes. Amazon opens automatically. OpenSight searched for omega-3 fish oil — you never said it. It gives you three options with prices.

**3.** `"Open the first one"`

> Amazon navigates to the product page. Ingredients are scraped in the background.

**4.** `"What are the ingredients"`

> OpenSight answers from the live page — no web search, no guessing.

---

## Wake word

At any point, say **"OpenSight"** and the app comes to the foreground ready to listen.

## Reset between runs

```bash
# wipe session memory for a clean demo
uvicorn server:app --host 127.0.0.1 --port 8080 --fresh
```