import asyncio, json, time, websockets, sys
sys.stdout.reconfigure(encoding='utf-8')

WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"

async def query(text, timeout=35, retries=3):
    await asyncio.sleep(2)
    for attempt in range(retries):
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({"text": text}))
                statuses = []
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                    if msg.get("type") == "status":
                        statuses.append(msg.get("agent", ""))
                    elif msg.get("type") == "response":
                        resp = msg.get("text", "")
                        if "models unavailable" in resp or "ran into an issue" in resp or "RESOURCE_EXHAUSTED" in resp:
                            print(f"  [RATE LIMIT] attempt {attempt+1}, waiting 60s...")
                            await asyncio.sleep(60)
                            break
                        return statuses, resp
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(15)
            else:
                return [], f"ERROR: {e}"
    return [], "RATE_LIMITED_AFTER_RETRIES"

async def query_routing_only(text, deadline=12):
    await asyncio.sleep(2)
    try:
        async with websockets.connect(WS_URL) as ws:
            await ws.send(json.dumps({"text": text}))
            t0 = time.time()
            agents = []
            while time.time() - t0 < deadline:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
                    if msg.get("type") == "status" and msg.get("agent") not in ("BRAIN", "IDLE"):
                        agents.append(msg.get("agent"))
                        return agents, "ROUTING_ONLY"
                except asyncio.TimeoutError:
                    if agents:
                        return agents, "ROUTING_ONLY"
                    continue
            return agents, "ROUTING_ONLY"
    except Exception as e:
        return [], f"ERROR: {e}"

results = []

def record(test_id, query_text, routing, response, passed, note):
    status = "PASS" if passed else "FAIL"
    results.append((test_id, query_text[:45], status, note))
    print(f"  [{status}] {test_id}: {note}")
    print(f"         Routing: {routing}")
    print(f"         Response: {response[:120]}...")

async def main():
    print("===== STARTING EVAL =====")
    print(f"Time: {time.strftime('%H:%M:%S')}\n")

    # ── GROUP 1: RESEARCH -> GENERAL ─────────────────────────────────────────
    print("--- GROUP 1: RESEARCH -> GENERAL ---")

    routing, resp = await query("Find me research on the gut-brain axis and mental health")
    passed = "RESEARCH" in routing and ("paper" in resp.lower() or "papers" in resp.lower())
    record("1a", "Find me research on gut-brain axis and mental health", routing, resp, passed,
           "RESEARCH+papers" if passed else f"routing={routing}, papers={'paper' in resp.lower()}")

    routing, resp = await query("What neurotransmitters are involved in that connection?")
    passed = any(k in resp.lower() for k in ["serotonin","dopamine","neurotransmitter","gut"])
    bad = resp.lower().startswith("got two papers") or resp.lower().startswith("found one paper")
    passed = passed and not bad
    record("1b", "What neurotransmitters are involved in that?", routing, resp, passed,
           "context-aware answer" if passed else f"no neuro context or fresh-search signal")

    routing, resp = await query("Is there a supplement that supports that pathway?")
    passed = any(k in resp.lower() for k in ["supplement","gut","microbiome","probiotic","prebiotic"])
    record("1c", "Is there a supplement that supports that pathway?", routing, resp, passed,
           "context-aware supplement" if passed else f"missing context keywords")

    routing, resp = await query("How long does it typically take to see results?")
    passed = len(resp) > 30 and "referring" not in resp.lower()
    record("1d", "How long does it typically take?", routing, resp, passed,
           "contextual answer" if passed else f"lost context or too short: {len(resp)} chars")

    await asyncio.sleep(15)

    # ── GROUP 2: RESEARCH -> SHOPPING ────────────────────────────────────────
    print("--- GROUP 2: RESEARCH -> SHOPPING ---")

    routing, resp = await query("Find me research on ashwagandha and stress reduction")
    passed = "RESEARCH" in routing and "ashwagandha" in resp.lower()
    record("2a", "Find me research on ashwagandha and stress", routing, resp, passed,
           "RESEARCH+ashwagandha" if passed else f"routing={routing}, ashwa={'ashwagandha' in resp.lower()}")

    routing, resp = await query_routing_only("Find me a supplement for that under $25")
    passed = "SHOPPING" in routing
    record("2b", "Find me a supplement for that under $25", routing, resp, passed,
           "SHOPPING routed" if passed else f"routing={routing}")

    routing, resp = await query_routing_only("What about under $15 instead?")
    passed = "SHOPPING" in routing
    record("2c", "What about under $15 instead?", routing, resp, passed,
           "SHOPPING re-routed" if passed else f"routing={routing}")

    routing, resp = await query("Find me research on rhodiola and fatigue")
    passed = "RESEARCH" in routing and "rhodiola" in resp.lower()
    record("2d", "Find me research on rhodiola and fatigue", routing, resp, passed,
           "RESEARCH+rhodiola" if passed else f"routing={routing}, rhodiola={'rhodiola' in resp.lower()}")

    routing, resp = await query_routing_only("Find me a supplement for that under $30")
    passed = "SHOPPING" in routing
    record("2e", "Find me a supplement for that under $30", routing, resp, passed,
           "SHOPPING routed (rhodiola ctx)" if passed else f"routing={routing}")

    await asyncio.sleep(15)

    # ── GROUP 3: SHOPPING -> GENERAL ─────────────────────────────────────────
    print("--- GROUP 3: SHOPPING -> GENERAL ---")

    routing, resp = await query_routing_only("Find me a standing desk under $400")
    passed = "SHOPPING" in routing
    record("3a", "Find me a standing desk under $400", routing, resp, passed,
           "SHOPPING routed" if passed else f"routing={routing}")

    routing, resp = await query("What are the health benefits of standing desks?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["stand","desk","posture","health","back"])
    record("3b", "What are the health benefits of standing desks?", routing, resp, passed,
           "GENERAL+desk context" if passed else f"routing={routing}, desk_kw={'stand' in resp.lower()}")

    routing, resp = await query("How many hours a day should I use one?")
    passed = any(k in resp.lower() for k in ["hour","time","stand","break","desk"])
    record("3c", "How many hours a day should I use one?", routing, resp, passed,
           "'one'->desk resolved" if passed else "no desk context")

    routing, resp = await query("Are there any downsides?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["downside","risk","fatigue","pain","discomfort","however","negati","concern"])
    record("3d", "Are there any downsides?", routing, resp, passed,
           "GENERAL+downsides" if passed else f"routing={routing}, kw match={any(k in resp.lower() for k in ['downside','risk','fatigue','pain','discomfort','however'])}")

    await asyncio.sleep(15)

    # ── GROUP 4: GENERAL -> RESEARCH ─────────────────────────────────────────
    print("--- GROUP 4: GENERAL -> RESEARCH ---")

    routing, resp = await query("What is BDNF and why does it matter?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["brain","neurotrophic","bdnf","memory","cognitive"])
    record("4a", "What is BDNF and why does it matter?", routing, resp, passed,
           "GENERAL+BDNF" if passed else f"routing={routing}")

    routing, resp = await query("Find me research on that")
    passed = "RESEARCH" in routing and any(k in resp.lower() for k in ["bdnf","brain","neurotrophic"])
    record("4b", "Find me research on that (BDNF)", routing, resp, passed,
           "RESEARCH+BDNF" if passed else f"routing={routing}, bdnf={'bdnf' in resp.lower()}")

    routing, resp = await query("What did the first paper find about exercise?")
    bad = resp.lower().startswith("got two papers") or resp.lower().startswith("found one paper")
    passed = "RESEARCH" in routing and not bad
    record("4c", "What did the first paper find about exercise?", routing, resp, passed,
           "RESEARCH followup, not fresh search" if passed else f"routing={routing}, fresh_search={bad}")

    routing, resp = await query("What foods increase it naturally?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["food","diet","exercise","blueberr","fish","bdnf"])
    record("4d", "What foods increase it naturally? (BDNF)", routing, resp, passed,
           "GENERAL+food context" if passed else f"routing={routing}, food={'food' in resp.lower()}")

    await asyncio.sleep(15)

    # ── GROUP 5: GENERAL -> SHOPPING ─────────────────────────────────────────
    print("--- GROUP 5: GENERAL -> SHOPPING ---")

    routing, resp = await query("I've been having trouble sleeping lately")
    passed = "GENERAL" in routing and len(resp) > 20
    record("5a", "I've been having trouble sleeping lately", routing, resp, passed,
           "GENERAL+sleep context" if passed else f"routing={routing}, len={len(resp)}")

    routing, resp = await query("What supplements are typically recommended for that?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["sleep","melatonin","magnesium","valerian","supplement"])
    record("5b", "What supplements recommended for that? (sleep)", routing, resp, passed,
           "GENERAL+sleep supplements" if passed else f"routing={routing}, supp_kw={'melatonin' in resp.lower()}")

    routing, resp = await query_routing_only("Find me one of those under $20")
    passed = "SHOPPING" in routing
    record("5c", "Find me one of those under $20 (sleep)", routing, resp, passed,
           "SHOPPING routed" if passed else f"routing={routing}")

    routing, resp = await query_routing_only("Actually I want a natural option specifically")
    passed = "SHOPPING" in routing
    record("5d", "Actually I want a natural option specifically", routing, resp, passed,
           "SHOPPING with natural constraint" if passed else f"routing={routing}")

    await asyncio.sleep(15)

    # ── GROUP 6: MULTI-HOP RESEARCH -> GENERAL -> RESEARCH ───────────────────
    print("--- GROUP 6: MULTI-HOP ---")

    routing, resp = await query("Find me research on intermittent fasting and longevity")
    passed = "RESEARCH" in routing
    record("6a", "Find me research on IF and longevity", routing, resp, passed,
           "RESEARCH routed" if passed else f"routing={routing}")

    routing, resp = await query("How does caloric restriction relate to that?")
    passed = "GENERAL" in routing and any(k in resp.lower() for k in ["caloric","restriction","fasting","longevity","calorie"])
    record("6b", "How does caloric restriction relate to that?", routing, resp, passed,
           "GENERAL+CR/IF bridge" if passed else f"routing={routing}, kw={any(k in resp.lower() for k in ['caloric','fasting','longevity'])}")

    routing, resp = await query("Are there studies specifically on caloric restriction in humans?")
    passed = "RESEARCH" in routing and "caloric" in resp.lower()
    record("6c", "Studies on caloric restriction in humans?", routing, resp, passed,
           "RESEARCH+caloric" if passed else f"routing={routing}, caloric={'caloric' in resp.lower()}")

    routing, resp = await query("How does the first paper compare to what we discussed earlier about IF?")
    passed = "RESEARCH" in routing and len(resp) > 40
    record("6d", "First paper vs IF discussion (multi-hop)", routing, resp, passed,
           "RESEARCH+multi-hop synthesis" if passed else f"routing={routing}, len={len(resp)}")

    await asyncio.sleep(15)

    # ── GROUP 7: RAPID AGENT SWITCHING ───────────────────────────────────────
    print("--- GROUP 7: RAPID SWITCHING ---")

    routing, resp = await query("What is melatonin?")
    passed = "GENERAL" in routing and "melatonin" in resp.lower()
    record("7a", "What is melatonin?", routing, resp, passed,
           "GENERAL+melatonin" if passed else f"routing={routing}")

    routing, resp = await query("Find me research on it")
    passed = "RESEARCH" in routing and "melatonin" in resp.lower()
    record("7b", "Find me research on it (melatonin)", routing, resp, passed,
           "RESEARCH+'it'->melatonin" if passed else f"routing={routing}, melatonin={'melatonin' in resp.lower()}")

    routing, resp = await query_routing_only("Find me a supplement for that under $15")
    passed = "SHOPPING" in routing
    record("7c", "Find me a supplement for that under $15", routing, resp, passed,
           "SHOPPING routed" if passed else f"routing={routing}")

    routing, resp = await query("What is the recommended dosage?")
    passed = any(k in resp.lower() for k in ["melatonin","dosage","mg","dose","milligram"])
    record("7d", "What is the recommended dosage? (melatonin)", routing, resp, passed,
           "melatonin dosage context" if passed else "no melatonin context in answer")

    routing, resp = await query("Find me research on valerian root instead")
    passed = "RESEARCH" in routing and "valerian" in resp.lower()
    record("7e", "Find me research on valerian root instead", routing, resp, passed,
           "RESEARCH+valerian, topic switch" if passed else f"routing={routing}, valerian={'valerian' in resp.lower()}")

    routing, resp = await query_routing_only("Find me a supplement for that")
    passed = "SHOPPING" in routing
    record("7f", "Find me a supplement for that (valerian)", routing, resp, passed,
           "SHOPPING routed (valerian ctx)" if passed else f"routing={routing}")

    routing, resp = await query("What is the capital of Iceland?")
    passed = ("GENERAL" in routing and "reykjavik" in resp.lower()
              and "melatonin" not in resp.lower() and "valerian" not in resp.lower())
    record("7g", "What is the capital of Iceland?", routing, resp, passed,
           "clean pivot, Reykjavik, no bleed" if passed else f"reykjavik={'reykjavik' in resp.lower()}, bleed={'melatonin' in resp.lower() or 'valerian' in resp.lower()}")

    routing, resp = await query("Find me research on that")
    passed = "RESEARCH" in routing and any(k in resp.lower() for k in ["iceland","reykjavik"])
    record("7h", "Find me research on that (Iceland)", routing, resp, passed,
           "RESEARCH+'that'->Iceland" if passed else f"routing={routing}, iceland={'iceland' in resp.lower()}")

    await asyncio.sleep(15)

    # ── GROUP 8: PRONOUN RESOLUTION ──────────────────────────────────────────
    print("--- GROUP 8: PRONOUN RESOLUTION ---")

    # 8a: reset -> photosynthesis -> research on that
    await query("What is the weather like today?")
    await asyncio.sleep(3)
    await query("What is photosynthesis?")
    routing, resp = await query("Find me research on that")
    passed = "RESEARCH" in routing and "photosynthesis" in resp.lower()
    record("8a", "photosynthesis -> research on that", routing, resp, passed,
           "RESEARCH+photosynthesis" if passed else f"routing={routing}, photo={'photosynthesis' in resp.lower()}")

    # 8b: reset -> vitamin D research -> second one
    await query("What is the weather like today?")
    await asyncio.sleep(3)
    await query("Find me research on vitamin D and bone health")
    routing, resp = await query("Tell me more about the second one")
    bad = resp.lower().startswith("got two papers") or resp.lower().startswith("found one paper")
    passed = "RESEARCH" in routing and not bad
    record("8b", "vitD research -> tell me about the second one", routing, resp, passed,
           "RESEARCH followup paper 2" if passed else f"routing={routing}, fresh_search={bad}")

    # 8c: reset -> zinc research -> supplement for that
    await query("What is the weather like today?")
    await asyncio.sleep(3)
    await query("Find me research on zinc and immunity")
    routing, resp = await query_routing_only("Find me a supplement for that")
    passed = "SHOPPING" in routing
    record("8c", "zinc research -> supplement for that", routing, resp, passed,
           "SHOPPING routed (zinc ctx)" if passed else f"routing={routing}")

    # 8d: reset -> collagen general -> supplement for that
    await query("What is the weather like today?")
    await asyncio.sleep(3)
    await query("What is collagen?")
    routing, resp = await query_routing_only("Is there a supplement for that?")
    passed = "SHOPPING" in routing or "GENERAL" in routing
    record("8d", "collagen -> supplement for that", routing, resp, passed,
           f"routed to {routing}" if passed else f"routing={routing}")

    # 8e: reset -> CoQ10 research -> shopping -> first one
    await query("What is the weather like today?")
    await asyncio.sleep(3)
    await query("Find me research on CoQ10 and heart health")
    await query_routing_only("Find me a supplement for that under $40")
    routing, resp = await query("Tell me more about the first one")
    passed = "SHOPPING" in routing or "GENERAL" in routing
    record("8e", "CoQ10: research+shop -> first one", routing, resp, passed,
           f"routed to {routing}" if passed else f"routing={routing}")

    await asyncio.sleep(15)

    # ── GROUP 9: NEGATIVE CASES ───────────────────────────────────────────────
    print("--- GROUP 9: NEGATIVE CASES ---")

    await query("Find me research on turmeric and inflammation")
    routing, resp = await query("What is the GDP of Germany?")
    passed = ("GENERAL" in routing and "germany" in resp.lower()
              and "turmeric" not in resp.lower())
    record("9a", "turmeric research -> GDP of Germany", routing, resp, passed,
           "clean pivot to GDP" if passed else f"routing={routing}, turmeric_bleed={'turmeric' in resp.lower()}")

    await query("Find me research on berberine and blood sugar")
    routing, resp = await query("Tell me a joke")
    passed = "GENERAL" in routing and "berberine" not in resp.lower()
    record("9b", "berberine research -> tell me a joke", routing, resp, passed,
           "clean joke, no bleed" if passed else f"routing={routing}, bleed={'berberine' in resp.lower()}")

    await query("Find me research on creatine and muscle growth")
    routing, resp = await query("Find me research on sleep and memory")
    passed = "RESEARCH" in routing and "sleep" in resp.lower() and "creatine" not in resp.lower()
    record("9c", "creatine -> sleep research (no bleed)", routing, resp, passed,
           "RESEARCH+sleep, creatine cleared" if passed else f"routing={routing}, creatine_bleed={'creatine' in resp.lower()}, sleep={'sleep' in resp.lower()}")

    routing, resp = await query("Find me research on ancient Rome")
    passed = "RESEARCH" in routing and any(k in resp.lower() for k in ["rome","roman","ancient"])
    record("9d", "Find me research on ancient Rome", routing, resp, passed,
           "RESEARCH+Rome" if passed else f"routing={routing}, rome={'rome' in resp.lower()}")

    # ── PRINT RESULTS ─────────────────────────────────────────────────────────
    print()
    print("===== CROSS-AGENT MEMORY EVAL RESULTS =====")
    print(f"{'Test':<6} {'Query':<47} {'Result':<7} Note")
    print("-" * 100)
    for tid, q, status, note in results:
        print(f"{tid:<6} {q:<47} {status:<7} {note}")

    groups = [
        ("RESEARCH -> GENERAL",  ["1a","1b","1c","1d"]),
        ("RESEARCH -> SHOPPING", ["2a","2b","2c","2d","2e"]),
        ("SHOPPING -> GENERAL",  ["3a","3b","3c","3d"]),
        ("GENERAL -> RESEARCH",  ["4a","4b","4c","4d"]),
        ("GENERAL -> SHOPPING",  ["5a","5b","5c","5d"]),
        ("Multi-hop chains",     ["6a","6b","6c","6d"]),
        ("Rapid switching",      ["7a","7b","7c","7d","7e","7f","7g","7h"]),
        ("Pronoun resolution",   ["8a","8b","8c","8d","8e"]),
        ("Negative cases",       ["9a","9b","9c","9d"]),
    ]

    print()
    print("===== SCORECARD =====")
    total_pass = 0
    total = 0
    for label, ids in groups:
        grp = [r for r in results if r[0] in ids]
        p = sum(1 for r in grp if r[2] == "PASS")
        t = len(grp)
        total_pass += p
        total += t
        print(f"  {label:<28}: {p}/{t}")
    print(f"  {'TOTAL':<28}: {total_pass}/{total}")

    print()
    print("===== TOP FAILURES =====")
    fails = [(tid, q, note) for tid, q, status, note in results if status == "FAIL"]
    if not fails:
        print("  No failures!")
    else:
        for tid, q, note in fails:
            print(f"  [{tid}] {q}")
            print(f"         Why: {note}")

    print(f"\nDone at {time.strftime('%H:%M:%S')}")

asyncio.run(main())

import os
os.remove("_tmp_eval.py")
print("Temp file deleted.")
print("File exists:", os.path.exists("_tmp_eval.py"))
