import asyncio
import json
import sys
import time
import websockets

# Force UTF-8 output so status messages with special chars don't crash on Windows
sys.stdout.reconfigure(encoding='utf-8')

WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"

async def query(text, timeout=45):
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"text": text}))
        statuses = []
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
            if msg.get("type") == "status":
                statuses.append(f"{msg.get('agent')} → {msg.get('detail')}")
            elif msg.get("type") == "response":
                return statuses, msg.get("text", "")

async def run_test(label, text, expected_note):
    print(f"\n{'='*70}")
    print(f"TEST {label}: {text}")
    print(f"Expected: {expected_note}")
    try:
        t0 = time.time()
        statuses, response = await query(text)
        elapsed = time.time() - t0
        print(f"TIME: {elapsed:.1f}s")
        print(f"ROUTING: {' | '.join(statuses) if statuses else '(no status msgs)'}")
        print(f"RESPONSE: {response}")
    except asyncio.TimeoutError:
        print("RESULT: TIMEOUT")
    except Exception as e:
        print(f"RESULT: ERROR — {e}")
    print(f"{'='*70}")

async def main():
    print("\n" + "="*70)
    print("OPENSIGHT MEMORY TEST SUITE")
    print(f"Backend: {WS_URL}")
    print("="*70)

    print("\n\n### GROUP 1 — Basic research memory persistence ###")
    await run_test("1a", "Find me research on omega-3 and brain health",
                   "RESEARCH, returns 2-3 paper titles")
    await run_test("1b", "Who wrote the first paper?",
                   "RESEARCH followup, returns author from cached papers")
    await run_test("1c", "What journal was it published in?",
                   "RESEARCH followup, returns journal name")
    await run_test("1d", "What were the main findings?",
                   "RESEARCH followup, returns findings from paper 1 specifically")
    await run_test("1e", "Tell me about the second one",
                   "RESEARCH followup, shifts context to paper 2")

    print("\n\n### GROUP 2 — Cross-agent handoff memory (research → shopping) ###")
    await run_test("2a", "Find me research on magnesium and sleep quality",
                   "RESEARCH")
    await run_test("2b", "Find me a supplement for that under $25",
                   "SHOPPING, query contains 'magnesium' NOT literal 'for that'")
    await run_test("2c", "What is the price of the second option?",
                   "SHOPPING followup, returns price of option 2")
    await run_test("2d", "Open the third one",
                   "SHOPPING followup, opens product 3")
    await run_test("2e", "What are the ingredients?",
                   "GENERAL with product context, returns specific ingredients")

    print("\n\n### GROUP 3 — Memory contamination ###")
    await run_test("3a", "Find me research on vitamin C and immune function",
                   "RESEARCH (fresh, not contaminated by GROUP 2)")
    await run_test("3b", "Find me a laptop under $600",
                   "SHOPPING (fresh search, NOT magnesium/supplement terms)")
    await run_test("3c", "What is the capital of Japan?",
                   "GENERAL, returns 'Tokyo' — no product/research context")
    await run_test("3d", "Find me research on that",
                   "GENERAL or RESEARCH on Japan/Tokyo — NOT vitamin C or magnesium")

    print("\n\n### GROUP 4 — Shopping memory edge cases ###")
    await run_test("4a", "Find me wireless headphones under $100",
                   "SHOPPING, returns 2-3 options")
    await run_test("4b", "Repeat the options",
                   "SHOPPING followup, lists all options with prices")
    await run_test("4c", "Tell me more about the first one",
                   "SHOPPING followup, details about headphones option 1")
    await run_test("4d", "Actually find me ones under $50 instead",
                   "SHOPPING with new price constraint, fresh Amazon search")
    await run_test("4e", "Open the second one",
                   "SHOPPING followup on NEW $50 results, not old $100 results")

    print("\n\n### GROUP 5 — Memory decay and ambiguity ###")
    await run_test("5a", "Find me research on creatine and muscle growth",
                   "RESEARCH")
    await run_test("5b", "Find me a supplement for that",
                   "SHOPPING, searches creatine supplement, NO price filter")
    await run_test("5c", "Open it",
                   "Asks 'which one' NOT silently opens first")
    await run_test("5d", "The second one",
                   "SHOPPING followup, opens option 2")
    await run_test("5e", "What are the benefits of creatine?",
                   "GENERAL — answers from product context or knowledge, NOT re-search")

    print("\n\n### GROUP 6 — Stress test: rapid context switching ###")
    await run_test("6a", "Find me research on turmeric and inflammation",
                   "RESEARCH on turmeric")
    await run_test("6b", "Find me a turmeric supplement under $20",
                   "SHOPPING for turmeric supplement")
    await run_test("6c", "Open the first one",
                   "SHOPPING followup, opens product 1")
    await run_test("6d", "What is the capital of France?",
                   "GENERAL, returns Paris — completely unrelated")
    await run_test("6e", "What are the ingredients?",
                   "GENERAL with product context (product page still open)")
    await run_test("6f", "Find me research on zinc and immunity",
                   "RESEARCH on zinc — NOT turmeric, NOT France")
    await run_test("6g", "Find me a supplement for that",
                   "SHOPPING for zinc supplement — NOT turmeric")

    print("\n\nDONE — review output above for pass/fail analysis")

asyncio.run(main())
