import asyncio
import json
import sys
import time
import websockets

sys.stdout.reconfigure(encoding='utf-8')

WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"

async def query(text, timeout=45):
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"text": text}))
        statuses = []
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("type") == "status":
                statuses.append(f"{msg.get('agent')} -> {msg.get('detail')}")
            elif msg.get("type") == "response":
                return statuses, msg.get("text", "")

results = []

async def run_test(label, text, expected_note):
    print(f"\n{'='*72}")
    print(f"TEST {label}: {text}")
    print(f"Expected: {expected_note}")
    routing_str = "(none)"
    response_str = ""
    try:
        t0 = time.time()
        statuses, response = await query(text)
        elapsed = time.time() - t0
        routing_str = " | ".join(statuses) if statuses else "(no status msgs)"
        response_str = response
        print(f"TIME:     {elapsed:.1f}s")
        print(f"ROUTING:  {routing_str}")
        print(f"RESPONSE: {response}")
    except asyncio.TimeoutError:
        response_str = "TIMEOUT"
        print(f"RESULT:   TIMEOUT (>45s)")
    except Exception as e:
        response_str = f"ERROR: {e}"
        print(f"RESULT:   ERROR -- {e}")
    results.append((label, text, expected_note, routing_str, response_str))
    print(f"{'='*72}")

async def main():
    print("\n" + "="*72)
    print("OPENSIGHT MEMORY TEST SUITE v2  —  Groups A-F (36 tests)")
    print(f"Backend: {WS_URL}")
    print("="*72)

    # ── GROUP A ────────────────────────────────────────────────────────────
    print("\n\n### GROUP A — Research memory, fresh topics ###")

    await run_test("A1",
        "Find me research on sleep deprivation and cognitive performance",
        "RESEARCH, 2 papers on sleep/cognition — NOT supplements or prior topics")

    await run_test("A2",
        "How many participants were in the first study?",
        "RESEARCH followup — attempts answer from cached sleep paper, NOT 'I have no info'")

    await run_test("A3",
        "What university conducted it?",
        "RESEARCH followup — paper metadata, must NOT route to GENERAL or SHOPPING")

    await run_test("A4",
        "Is the second paper more recent?",
        "RESEARCH followup — compares publication years of both papers")

    await run_test("A5",
        "Find me research on intermittent fasting and weight loss",
        "RESEARCH on new topic — fully replaces sleep context, no blending")

    await run_test("A6",
        "What were the findings of the first paper?",
        "RESEARCH followup — findings from intermittent fasting paper, NOT sleep paper")

    # ── GROUP B ────────────────────────────────────────────────────────────
    print("\n\n### GROUP B — Shopping non-supplement, stale memory check ###")

    await run_test("B1",
        "Find me a standing desk under $400",
        "SHOPPING — desk options, NOT supplements. Timeout expected on Cloud Run; record cleanly")

    await run_test("B2",
        "What are the dimensions of the first one?",
        "SHOPPING followup OR clean error if B1 timed out — must NOT return supplement/laptop data")

    await run_test("B3",
        "Actually find me one under $300 instead",
        "New SHOPPING search with updated budget — fresh search")

    await run_test("B4",
        "Repeat the options",
        "SHOPPING followup listing desk options — NOT laptop or supplement stale data")

    # ── GROUP C ────────────────────────────────────────────────────────────
    print("\n\n### GROUP C — GENERAL agent context isolation ###")

    await run_test("C1",
        "Who invented the telephone?",
        "GENERAL — 'Alexander Graham Bell', no research/shopping bleed")

    await run_test("C2",
        "What year was it?",
        "GENERAL followup — resolves 'it' to telephone, returns ~1876")

    await run_test("C3",
        "How does it work?",
        "GENERAL followup — telephone mechanism, NOT supplements or research papers")

    await run_test("C4",
        "Find me research on that",
        "RESEARCH on telephone/telecommunications — NOT supplements")

    await run_test("C5",
        "What is photosynthesis?",
        "GENERAL — clean science explanation, no bleed from telephone or research context")

    await run_test("C6",
        "Can you explain it more simply?",
        "GENERAL followup — 'it' resolves to photosynthesis correctly")

    # ── GROUP D ────────────────────────────────────────────────────────────
    print("\n\n### GROUP D — Ambiguous followup resolution (hardest) ###")

    await run_test("D1",
        "Find me research on caffeine and athletic performance",
        "RESEARCH — papers on caffeine")

    await run_test("D2",
        "Find me a supplement for that",
        "SHOPPING for caffeine supplement — no price filter, query contains 'caffeine' not 'for that'")

    await run_test("D3",
        "Tell me more about the first one",
        "SHOPPING followup on first supplement option — NOT research paper (Bug 3 fix check)")

    await run_test("D4",
        "Who wrote the caffeine study?",
        "RESEARCH followup — switches back to research context for the caffeine papers")

    await run_test("D5",
        "Find me research on beta-alanine and endurance",
        "RESEARCH on new topic — caffeine papers fully replaced")

    await run_test("D6",
        "Find me one under $35",
        "SHOPPING for beta-alanine supplement under $35 — cross-agent handoff from new research")

    await run_test("D7",
        "Open the first one",
        "SHOPPING followup open — NOT research paper open (most recent agent = SHOPPING)")

    # ── GROUP E ────────────────────────────────────────────────────────────
    print("\n\n### GROUP E — Edge cases / graceful degradation ###")

    await run_test("E1", "Yes",
        "GENERAL graceful response — not rejected as garble")

    await run_test("E2", "No",
        "GENERAL graceful — not rejected")

    await run_test("E3", "Stop",
        "GENERAL graceful — not rejected")

    await run_test("E4", "What?",
        "GENERAL asking for clarification — not rejected")

    await run_test("E5", "Repeat",
        "SHOPPING followup if active, GENERAL otherwise — not rejected")

    await run_test("E6", "The third one",
        "SHOPPING followup if options exist, GENERAL if not — handled gracefully")

    await run_test("E7", "asdfjkl qwerty zxcvbn",
        "Garble rejection — 'I didn't catch that' or similar")

    await run_test("E8", "um",
        "Garble rejection — too short/not actionable")

    # ── GROUP F ────────────────────────────────────────────────────────────
    print("\n\n### GROUP F — Memory persistence correctness ###")

    await run_test("F1",
        "Find me research on Alzheimer's and sleep",
        "RESEARCH — papers on Alzheimer's/sleep")

    await run_test("F2",
        "Find me a supplement for that under $50",
        "SHOPPING — sleep/brain supplement hint, NOT Alzheimer's medication. Note Amazon search query if visible")

    await run_test("F3",
        "What is the capital of Australia?",
        "GENERAL — 'Canberra', zero bleed from Alzheimer's or supplement context")

    await run_test("F4",
        "Find me research on that",
        "RESEARCH on Australia/Canberra — 'that' resolves to most recent GENERAL topic, NOT Alzheimer's")

    await run_test("F5",
        "Find me research on gut microbiome and mental health",
        "RESEARCH — new topic, cleanly replaces Australia context")

    await run_test("F6",
        "What were the key findings?",
        "RESEARCH followup on gut microbiome — NOT Alzheimer's, NOT Australia")

    await run_test("F7",
        "Find me a probiotic for that under $40",
        "SHOPPING for probiotic under $40 — cross-agent handoff from gut microbiome research")

    # ── SUMMARY ────────────────────────────────────────────────────────────
    print("\n\n" + "="*72)
    print("RAW RESULTS DUMP (label | routing | response)")
    print("="*72)
    for label, text, expected, routing, response in results:
        print(f"\n[{label}] Q: {text}")
        print(f"      Routing:  {routing}")
        print(f"      Response: {response}")
        print(f"      Expected: {expected}")

    print("\n\nDONE")

asyncio.run(main())
