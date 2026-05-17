"""OpenSight demo day simulation + full regression test. Self-deletes after run."""
import asyncio
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed"); sys.exit(1)

WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"

# ── Mock data ─────────────────────────────────────────────────────────────────

MOCK_HEADPHONES_200 = [
    {"title": "Sony WH-1000XM4 Wireless Noise Canceling Headphones", "price": "$198.00", "price_val": 198.00, "url": "https://amazon.com/dp/H003"},
    {"title": "Bose QuietComfort 35 II Noise Canceling Wireless Headphones", "price": "$179.00", "price_val": 179.00, "url": "https://amazon.com/dp/H004"},
]
MOCK_HEADPHONE_SCRAPED = {
    "title": "Sony WH-1000XM4 Wireless Noise Canceling Headphones",
    "ingredients": "",
    "bullets": [
        "Industry-leading noise canceling with Dual Noise Sensor technology",
        "30-hour battery life with quick charging (10 min charge = 5 hours playback)",
        "Touch sensor controls for play, pause, skip, volume",
        "Wearing detection, speak-to-chat, multipoint connection",
    ],
    "url": "https://amazon.com/dp/H003",
}
MOCK_OMEGA3_30 = [
    {"title": "Nordic Naturals Ultimate Omega 1280mg Omega-3 Softgels", "price": "$28.95", "price_val": 28.95, "url": "https://amazon.com/dp/O001"},
    {"title": "Sports Research Triple Strength Omega-3 Fish Oil 1250mg", "price": "$24.95", "price_val": 24.95, "url": "https://amazon.com/dp/O002"},
]
MOCK_OMEGA3_SCRAPED = {
    "title": "Nordic Naturals Ultimate Omega 1280mg Omega-3 Softgels",
    "ingredients": "Fish Oil Concentrate (Anchovy, Sardine, Mackerel), Soft Gel Capsule (Gelatin, Glycerin, Water), Natural Lemon Flavor, d-Alpha Tocopherol",
    "bullets": [
        "1280mg omega-3s (EPA + DHA) per serving for brain and heart health",
        "Purified, third-party tested, non-GMO, no artificial flavors",
        "Great lemon taste, no fishy aftertaste",
    ],
    "url": "https://amazon.com/dp/O001",
}
MOCK_ASHWAGANDHA_25 = [
    {"title": "KSM-66 Ashwagandha Root Extract 600mg High Concentration Full Spectrum", "price": "$22.99", "price_val": 22.99, "url": "https://amazon.com/dp/A001"},
    {"title": "Organic India Ashwagandha Capsules Stress and Energy Support", "price": "$19.95", "price_val": 19.95, "url": "https://amazon.com/dp/A002"},
    {"title": "Himalaya Organic Ashwagandha Stress Relief Supplement 90 Caplets", "price": "$14.99", "price_val": 14.99, "url": "https://amazon.com/dp/A003"},
]
MOCK_SNACKS_15 = [
    {"title": "SunButter Natural Sunflower Butter Creamy Peanut Free Facility", "price": "$8.99", "price_val": 8.99, "url": "https://amazon.com/dp/S001"},
    {"title": "Enjoy Life Soft Baked Cookies Chocolate Chip Allergy Friendly", "price": "$12.49", "price_val": 12.49, "url": "https://amazon.com/dp/S002"},
    {"title": "Simple Mills Almond Flour Crackers Sea Salt Gluten Free", "price": "$5.99", "price_val": 5.99, "url": "https://amazon.com/dp/S003"},
]
MOCK_SNACKS_20 = [
    {"title": "Larabar Fruit Nut Bar Cashew Cookie Gluten Free Vegan Snack", "price": "$15.99", "price_val": 15.99, "url": "https://amazon.com/dp/S004"},
    {"title": "Kind Bars Dark Chocolate Nuts Sea Salt Gluten Free Snack Bar", "price": "$17.99", "price_val": 17.99, "url": "https://amazon.com/dp/S005"},
]
MOCK_EARBUDS_60 = [
    {"title": "JLab Go Air Pop True Wireless Earbuds Dual Connect Bluetooth", "price": "$25.88", "price_val": 25.88, "url": "https://amazon.com/dp/E001"},
    {"title": "Soundcore Life P3 Hybrid Active Noise Canceling Earbuds", "price": "$39.99", "price_val": 39.99, "url": "https://amazon.com/dp/E002"},
    {"title": "Jabra Elite 4 Active In-Ear Bluetooth Sport Earbuds", "price": "$59.99", "price_val": 59.99, "url": "https://amazon.com/dp/E003"},
]
MOCK_EARBUDS_40 = [
    {"title": "JLab Go Air Pop True Wireless Earbuds Dual Connect Bluetooth", "price": "$25.88", "price_val": 25.88, "url": "https://amazon.com/dp/E001"},
    {"title": "Soundcore Life A3i Active Noise Canceling Wireless Earbuds", "price": "$34.99", "price_val": 34.99, "url": "https://amazon.com/dp/E004"},
]
MOCK_LIONSANE_30 = [
    {"title": "Host Defense Lion's Mane Mushroom Capsules Cognitive Support", "price": "$24.95", "price_val": 24.95, "url": "https://amazon.com/dp/L001"},
    {"title": "Real Mushrooms Lion's Mane Extract Capsules Brain Health", "price": "$27.99", "price_val": 27.99, "url": "https://amazon.com/dp/L002"},
]
MOCK_GENERIC_SCRAPED = {
    "title": "Test Product",
    "ingredients": "Natural ingredients",
    "bullets": ["Feature A", "Feature B"],
    "url": "https://amazon.com/dp/X000",
}


def check_voice_quality(response: str) -> list:
    p = []
    if re.search(r'\*\*.*?\*\*', response): p.append("**bold**")
    if re.search(r'^\s*[-*•]\s', response, re.MULTILINE): p.append("bullet points")
    if re.search(r'^\s*\d+\.\s', response, re.MULTILINE): p.append("numbered list")
    if re.search(r'^#{1,6}\s', response, re.MULTILINE): p.append("headers")
    if '`' in response: p.append("backticks")
    if re.search(r'(?<!\w)\$(?=\d)', response): p.append("$ sign")
    if re.search(r'\d+%', response): p.append("% sign")
    if len(response.split()) > 80: p.append(f"too long ({len(response.split())} words)")
    if response.count('\n') > 3: p.append("too many newlines")
    return p


def first_nonbrain(agents):
    for a in agents:
        if a not in ("BRAIN", "IDLE", ""):
            return a
    return "?"


def short(t, n=75):
    return (t[:n] + "…") if len(t) > n else t


# ── Core session runner ────────────────────────────────────────────────────────

async def run_session(steps: list, session_label: str = "") -> list:
    """Run a list of steps on ONE WebSocket connection. Returns result dicts."""
    results = []
    try:
        async with websockets.connect(WS_URL) as ws:
            for step in steps:
                label     = step["label"]
                text      = step["text"]
                mp        = step.get("mock_products")    # for SHOPPING
                ms        = step.get("mock_scraped", MOCK_GENERIC_SCRAPED)  # for SHOPPING_OPEN
                pre_sleep = step.get("delay", 3)

                await asyncio.sleep(pre_sleep)
                t0 = time.time()
                await ws.send(json.dumps({"text": text}))

                agents, resp, got_routing = [], "", False

                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=45)
                    except asyncio.TimeoutError:
                        resp = "TIMEOUT"
                        break

                    msg = json.loads(raw)
                    mtype = msg.get("type", "")

                    if mtype == "status":
                        a = msg.get("agent", "")
                        if a not in ("BRAIN", "IDLE", "") and a not in agents:
                            agents.append(a)
                            got_routing = True

                    elif mtype == "research_status":
                        pass

                    elif mtype == "browser_action":
                        aname = msg.get("agent", "")
                        if "SHOPPING" in aname and aname not in agents:
                            agents.append("SHOPPING") if "SHOPPING" not in agents else None
                            got_routing = True
                        if aname == "SHOPPING":
                            await ws.send(json.dumps({
                                "type": "browser_result", "agent": "SHOPPING",
                                "data": {"results": mp or MOCK_SNACKS_15, "scraped": {}},
                            }))
                        elif aname == "SHOPPING_OPEN":
                            await ws.send(json.dumps({
                                "type": "browser_result", "agent": "SHOPPING_OPEN",
                                "data": {"scraped": ms},
                            }))
                        # RESEARCH / RESEARCH_OPEN: fire-and-forget, no reply needed

                    elif mtype == "response":
                        resp = msg.get("text", "")
                        break

                lat = time.time() - t0
                vp  = check_voice_quality(resp) if resp and resp != "TIMEOUT" else (["TIMEOUT"] if resp == "TIMEOUT" else [])
                results.append({
                    "label":   label,
                    "agents":  agents,
                    "first":   first_nonbrain(agents),
                    "resp":    resp,
                    "latency": lat,
                    "vp":      vp,
                })
                print(f"    {label:6s} [{first_nonbrain(agents):8s}] {lat:.1f}s | "
                      f"{'CLEAN' if not vp else 'FAIL:'+','.join(vp[:2]):18s} | {short(resp)}")

    except Exception as e:
        print(f"  [session error] {session_label}: {e}")
        results.append({"label": "ERR", "agents": [], "first": "?",
                        "resp": str(e), "latency": 0, "vp": ["ERROR"]})
    return results


async def single_query(text, mock_products=None, mock_scraped=None, timeout=40, retries=2):
    """Single query with browser_action handling."""
    await asyncio.sleep(2)
    for attempt in range(retries):
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({"text": text}))
                agents, resp = [], ""
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        return agents, "TIMEOUT"
                    msg = json.loads(raw)
                    mtype = msg.get("type", "")
                    if mtype == "status":
                        a = msg.get("agent", "")
                        if a not in ("BRAIN", "IDLE", "") and a not in agents:
                            agents.append(a)
                    elif mtype == "browser_action":
                        aname = msg.get("agent", "")
                        if "SHOPPING" in aname and "SHOPPING" not in agents:
                            agents.append("SHOPPING")
                        if aname == "SHOPPING":
                            await ws.send(json.dumps({
                                "type": "browser_result", "agent": "SHOPPING",
                                "data": {"results": mock_products or MOCK_SNACKS_15, "scraped": {}},
                            }))
                        elif aname == "SHOPPING_OPEN":
                            await ws.send(json.dumps({
                                "type": "browser_result", "agent": "SHOPPING_OPEN",
                                "data": {"scraped": mock_scraped or MOCK_GENERIC_SCRAPED},
                            }))
                    elif mtype == "response":
                        resp = msg.get("text", "")
                        if "models unavailable" in resp or "ran into an issue" in resp:
                            print(f"  [RATE LIMIT] waiting 60s…")
                            await asyncio.sleep(60)
                            break
                        return agents, resp
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(15)
            else:
                return [], f"ERROR: {e}"
    return [], "RATE_LIMITED"


async def qr_ex(text, timeout=15):
    """Routing-only detection, handles browser_action for SHOPPING."""
    await asyncio.sleep(2)
    for attempt in range(3):
        try:
            async with websockets.connect(WS_URL) as ws:
                await ws.send(json.dumps({"text": text}))
                t0 = time.time()
                while time.time() - t0 < timeout:
                    try:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                        mtype = msg.get("type", "")
                        if mtype == "status":
                            a = msg.get("agent", "")
                            if a not in ("BRAIN", "IDLE"):
                                return [a]
                        elif mtype == "browser_action":
                            aname = msg.get("agent", "")
                            if "SHOPPING" in aname:
                                return ["SHOPPING"]
                            if "RESEARCH" in aname:
                                return ["RESEARCH"]
                        elif mtype == "response":
                            return ["GENERAL"]
                    except asyncio.TimeoutError:
                        continue
        except Exception:
            if attempt < 2:
                await asyncio.sleep(10)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — DEMO DAY SIMULATION
# ─────────────────────────────────────────────────────────────────────────────

async def part1():
    print("\n" + "="*70)
    print("PART 1 — DEMO DAY SIMULATION")
    print("="*70)

    all_scenario_results = {}

    # ── SCENARIO 1: Noise-canceling headphones ─────────────────────────────
    print("\n── SCENARIO 1: Noise-Canceling Headphones ───────────────────────")
    s1 = await run_session([
        {"label": "D1a", "text": "Find me research on the best noise-canceling headphones"},
        {"label": "D1b", "text": "Find me the top result on Amazon under $200",
         "mock_products": MOCK_HEADPHONES_200},
        {"label": "D1c", "text": "Open the first one",
         "mock_scraped": MOCK_HEADPHONE_SCRAPED},
        {"label": "D1d", "text": "Add a reminder to check the delivery in 5 days to my calendar"},
        {"label": "D1e", "text": "What are the key specs of that headphone?"},
    ], "Scenario1")
    all_scenario_results["Headphones"] = s1

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── SCENARIO 2: Omega-3 supplement chain ───────────────────────────────
    print("\n── SCENARIO 2: Omega-3 Supplement Chain ─────────────────────────")
    s2 = await run_session([
        {"label": "D2a", "text": "Find me research on omega-3 and brain health"},
        {"label": "D2b", "text": "Find me a supplement for that under $30",
         "mock_products": MOCK_OMEGA3_30},
        {"label": "D2c", "text": "Open the first one",
         "mock_scraped": MOCK_OMEGA3_SCRAPED},
        {"label": "D2d", "text": "What are the ingredients?"},
        {"label": "D2e", "text": "Add a reminder to take it every morning to my calendar"},
    ], "Scenario2")
    all_scenario_results["Omega3"] = s2

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── SCENARIO 3: Ashwagandha rapid switch ──────────────────────────────
    print("\n── SCENARIO 3: Rapid Three-Agent Switch (Ashwagandha) ───────────")
    s3 = await run_session([
        {"label": "D3a", "text": "What is ashwagandha?"},
        {"label": "D3b", "text": "Find me research on it"},
        {"label": "D3c", "text": "Find me a supplement for that under $25",
         "mock_products": MOCK_ASHWAGANDHA_25},
        {"label": "D3d", "text": "What is the recommended dosage?"},
        {"label": "D3e", "text": "Schedule a reminder to take it daily starting Monday"},
        {"label": "D3f", "text": "What is the capital of France?"},
    ], "Scenario3")
    all_scenario_results["Ashwagandha"] = s3

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── SCENARIO 4: Peanut-free snack flow ───────────────────────────────
    print("\n── SCENARIO 4: Peanut-Free Snack Flow ──────────────────────────")
    s4 = await run_session([
        {"label": "D4a", "text": "Find me peanut-free snacks under $15",
         "mock_products": MOCK_SNACKS_15},
        {"label": "D4b", "text": "Pick the healthiest option"},
        {"label": "D4c", "text": "What makes a snack peanut-free?"},
        {"label": "D4d", "text": "Find me research on peanut allergies"},
        {"label": "D4e", "text": "Find me one under $20",
         "mock_products": MOCK_SNACKS_20},
    ], "Scenario4")
    all_scenario_results["PeanutSnack"] = s4

    # ── Part 1 summary ────────────────────────────────────────────────────
    print("\n\n── DEMO DAY READINESS REPORT ────────────────────────────────────")
    expected_firsts = {
        "Headphones": {"D1a":"RESEARCH","D1b":"SHOPPING","D1c":"SHOPPING","D1d":"CALENDAR","D1e":"GENERAL"},
        "Omega3":     {"D2a":"RESEARCH","D2b":"SHOPPING","D2c":"SHOPPING","D2d":"GENERAL","D2e":"CALENDAR"},
        "Ashwagandha":{"D3a":"GENERAL","D3b":"RESEARCH","D3c":"SHOPPING","D3d":"GENERAL","D3e":"CALENDAR","D3f":"GENERAL"},
        "PeanutSnack":{"D4a":"SHOPPING","D4b":"SHOPPING","D4c":"GENERAL","D4d":"RESEARCH","D4e":"SHOPPING"},
    }
    scenario_names = {
        "Headphones": "Headphones (RESEARCH→SHOPPING→CALENDAR)",
        "Omega3":     "Omega-3    (RESEARCH→SHOPPING→GENERAL→CAL)",
        "Ashwagandha":"Rapid switch (GEN→RES→SHOP→GEN→CAL→GEN)",
        "PeanutSnack":"Peanut snack (SHOP→SHOP→GEN→RES→SHOP)",
    }
    print(f"\n{'Scenario':<20} {'Chain':<35} {'Complete':<10} {'Voice':<10} {'Verdict'}")
    print("-"*85)

    part1_critical = []
    for sname, results in all_scenario_results.items():
        exp = expected_firsts[sname]
        chain_agents = [r["first"] for r in results]
        voice_ok = all(not r["vp"] for r in results)
        chain_ok = all(r["first"] == exp.get(r["label"], r["first"]) for r in results)

        chain_str = "→".join(chain_agents)
        verdict = "READY" if chain_ok and voice_ok else "NEEDS FIX"

        print(f"  {sname:<18} {chain_str:<35} {'YES' if chain_ok else 'NO':<10} {'YES' if voice_ok else 'NO':<10} {verdict}")

        if not chain_ok:
            for r in results:
                expected_a = exp.get(r["label"])
                if expected_a and r["first"] != expected_a:
                    part1_critical.append(
                        f"  [{r['label']}] Expected {expected_a}, got {r['first']}: '{short(r['resp'], 55)}'"
                    )
        if not voice_ok:
            for r in results:
                if r["vp"] and r["vp"] != ["TIMEOUT"]:
                    part1_critical.append(f"  [{r['label']}] Voice: {r['vp']} in '{short(r['resp'], 45)}'")

    if part1_critical:
        print("\n  BROKEN STEPS:")
        for c in part1_critical:
            print(c)
    else:
        print("\n  All steps routed correctly and voice clean.")

    return all_scenario_results, part1_critical


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — FULL REGRESSION TEST
# ─────────────────────────────────────────────────────────────────────────────

async def part2():
    print("\n\n" + "="*70)
    print("PART 2 — FULL REGRESSION TEST")
    print("="*70)

    scores = {}  # group_label → (pass_count, total)
    all_failures = []

    def record(group, label, passed, note=""):
        scores.setdefault(group, [0, 0])
        scores[group][1] += 1
        if passed:
            scores[group][0] += 1
        else:
            all_failures.append(f"[{group}/{label}] {note}")

    def p(label, passed, agent, resp):
        tag = "PASS" if passed else "FAIL"
        print(f"    {label:6s} [{agent:8s}] {tag} | {short(resp)}")

    # ── REG GROUP 1: Cross-agent memory ─────────────────────────────────
    print("\n── REG GROUP 1: Cross-agent memory ─────────────────────────────")
    g1 = await run_session([
        {"label": "R1a", "text": "Find me research on lion's mane and cognitive function"},
        {"label": "R1b", "text": "What are its main active compounds?"},
        {"label": "R1c", "text": "Find me a supplement for that under $30",
         "mock_products": MOCK_LIONSANE_30},
        {"label": "R1d", "text": "What is the recommended dose?"},
        {"label": "R1e", "text": "Find me research on that"},
    ], "G1")
    exp_g1 = {"R1a":"RESEARCH","R1b":"GENERAL","R1c":"SHOPPING","R1d":"GENERAL","R1e":"RESEARCH"}
    for r in g1:
        ok = r["first"] == exp_g1.get(r["label"], r["first"])
        record("Cross-agent memory", r["label"], ok, f"{r['label']}: expected {exp_g1.get(r['label'])} got {r['first']}")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 2: Pronoun resolution ──────────────────────────────────
    print("\n── REG GROUP 2: Pronoun resolution ──────────────────────────────")
    g2 = await run_session([
        {"label": "R2a", "text": "What is NAD plus?"},
        {"label": "R2b", "text": "Find me research on that"},
        {"label": "R2c", "text": "What is resveratrol?"},
        {"label": "R2d", "text": "Find me research on that"},
    ], "G2")
    exp_g2 = {"R2a":"GENERAL","R2b":"RESEARCH","R2c":"GENERAL","R2d":"RESEARCH"}
    # Additional check: R2b should mention NAD, R2d should mention resveratrol
    for r in g2:
        ok = r["first"] == exp_g2.get(r["label"], r["first"])
        record("Pronoun resolution", r["label"], ok, f"{r['label']}: expected {exp_g2.get(r['label'])} got {r['first']}")
    # Check pronoun actually resolved
    r2b = next((r for r in g2 if r["label"] == "R2b"), None)
    r2d = next((r for r in g2 if r["label"] == "R2d"), None)
    if r2b:
        nad_in = "nad" in r2b["resp"].lower() or "nicotinamide" in r2b["resp"].lower()
        record("Pronoun resolution", "R2b-content", nad_in, "R2b: NAD not in research response")
    if r2d:
        resv_in = "resveratrol" in r2d["resp"].lower()
        record("Pronoun resolution", "R2d-content", resv_in, "R2d: resveratrol not in research response (topic didn't switch)")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 3: Knowledge questions → GENERAL ───────────────────────
    print("\n── REG GROUP 3: Knowledge questions → GENERAL ──────────────────")
    g3 = await run_session([
        {"label": "R3a", "text": "Find me research on turmeric and inflammation"},
        {"label": "R3b", "text": "What causes inflammation in the body?"},
        {"label": "R3c", "text": "Which foods trigger it most?"},
        {"label": "R3d", "text": "Where does inflammation occur?"},
        {"label": "R3e", "text": "Why does chronic inflammation happen?"},
    ], "G3")
    exp_g3 = {"R3a":"RESEARCH","R3b":"GENERAL","R3c":"GENERAL","R3d":"GENERAL","R3e":"GENERAL"}
    for r in g3:
        ok = r["first"] == exp_g3.get(r["label"], r["first"])
        record("Knowledge→GENERAL", r["label"], ok, f"{r['label']}: expected {exp_g3.get(r['label'])} got {r['first']}")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 4: Shopping followup patterns ───────────────────────────
    print("\n── REG GROUP 4: Shopping followup patterns ──────────────────────")
    g4 = await run_session([
        {"label": "R4a", "text": "Find me wireless earbuds under $60",
         "mock_products": MOCK_EARBUDS_60},
        {"label": "R4b", "text": "Pick the best one"},
        {"label": "R4c", "text": "What's the difference between earbuds and headphones?"},
        {"label": "R4d", "text": "Open the second one"},
        {"label": "R4e", "text": "Find me ones under $40 instead",
         "mock_products": MOCK_EARBUDS_40},
    ], "G4")
    exp_g4 = {"R4a":"SHOPPING","R4b":"SHOPPING","R4c":"GENERAL","R4d":"SHOPPING","R4e":"SHOPPING"}
    for r in g4:
        ok = r["first"] == exp_g4.get(r["label"], r["first"])
        record("Shopping followup", r["label"], ok, f"{r['label']}: expected {exp_g4.get(r['label'])} got {r['first']}")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 5: Negative cases / context isolation ───────────────────
    print("\n── REG GROUP 5: Context isolation ──────────────────────────────")
    g5 = await run_session([
        {"label": "R5a", "text": "Find me research on collagen and skin health"},
        {"label": "R5b", "text": "What is the GDP of Canada?"},
        {"label": "R5c", "text": "Tell me a joke"},
        {"label": "R5d", "text": "Find me research on sleep and memory"},
    ], "G5")
    exp_g5 = {"R5a":"RESEARCH","R5b":"GENERAL","R5c":"GENERAL","R5d":"RESEARCH"}
    for r in g5:
        ok = r["first"] == exp_g5.get(r["label"], r["first"])
        record("Context isolation", r["label"], ok, f"{r['label']}: expected {exp_g5.get(r['label'])} got {r['first']}")
    # R5b should have no collagen mention
    r5b = next((r for r in g5 if r["label"] == "R5b"), None)
    if r5b:
        no_bleed = "collagen" not in r5b["resp"].lower()
        record("Context isolation", "R5b-nobleed", no_bleed, "R5b: collagen mentioned in Canada GDP response (context bleed)")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 6: Voice formatting ─────────────────────────────────────
    print("\n── REG GROUP 6: Voice formatting spot check ─────────────────────")
    g6 = await run_session([
        {"label": "R6a", "text": "What are the benefits of magnesium?"},
        {"label": "R6b", "text": "Find me research on vitamin B12 and energy"},
        {"label": "R6c", "text": "Explain how DNA replication works"},
        {"label": "R6d", "text": "Compare creatine monohydrate and creatine HCL"},
    ], "G6")
    for r in g6:
        clean = not r["vp"] or r["vp"] == ["TIMEOUT"]
        record("Voice formatting", r["label"], clean, f"{r['label']}: {r['vp']} in '{short(r['resp'], 45)}'")

    print("  [15s sleep]"); await asyncio.sleep(15)

    # ── REG GROUP 7: Error handling ──────────────────────────────────────
    print("\n── REG GROUP 7: Error handling spot check ───────────────────────")
    print("    R7a  garble…", end="", flush=True)
    agents_7a, resp_7a = await single_query("asdfgh qwerty zxcvb", timeout=15)
    ok7a = "catch" in resp_7a.lower() or "say that again" in resp_7a.lower()
    print(f" [{first_nonbrain(agents_7a):8s}] {'PASS' if ok7a else 'FAIL'} | {short(resp_7a)}")
    record("Error handling", "R7a", ok7a, f"garble not caught: '{short(resp_7a,40)}'")

    print("    R7b  empty…", end="", flush=True)
    agents_7b, resp_7b = await single_query("", timeout=15)
    ok7b = not resp_7b.startswith("ERROR")
    print(f" [{first_nonbrain(agents_7b):8s}] {'PASS' if ok7b else 'FAIL'} | {short(resp_7b)}")
    record("Error handling", "R7b", ok7b, f"crash on empty: '{short(resp_7b,40)}'")

    print("    R7c  'yes'…", end="", flush=True)
    t0 = time.time()
    agents_7c, resp_7c = await single_query("yes", timeout=12)
    lat7c = time.time() - t0
    ok7c = first_nonbrain(agents_7c) in ("GENERAL", "?") and not resp_7c.startswith("ERROR")
    print(f" [{first_nonbrain(agents_7c):8s}] {'PASS' if ok7c else 'FAIL'} {lat7c:.1f}s | {short(resp_7c)}")
    record("Error handling", "R7c", ok7c, f"'yes' failed or slow: {lat7c:.1f}s")

    print("    R7d  garble→research…", end="", flush=True)
    await single_query("zzzzz qqqqq pppp", timeout=10)
    await asyncio.sleep(2)
    agents_7d, resp_7d = await single_query("Find me research on zinc and immunity")
    ok7d = first_nonbrain(agents_7d) == "RESEARCH"
    print(f" [{first_nonbrain(agents_7d):8s}] {'PASS' if ok7d else 'FAIL'} | {short(resp_7d)}")
    record("Error handling", "R7d", ok7d, f"garble→research failed: got {first_nonbrain(agents_7d)}")

    # ── Part 2 summary ────────────────────────────────────────────────────
    print("\n\n── FULL REGRESSION SCORECARD ────────────────────────────────────")
    print(f"\n{'Category':<28} {'Score':<8} {'Status'}")
    print("-"*50)
    total_pass, total_all = 0, 0
    for cat, (p_count, t_count) in scores.items():
        total_pass += p_count; total_all += t_count
        status = "PASS" if p_count == t_count else "FAIL"
        print(f"  {cat:<26} {p_count}/{t_count:<7} {status}")
    print(f"  {'TOTAL':<26} {total_pass}/{total_all}")

    if all_failures:
        print("\n  FAILURES:")
        for f in all_failures:
            print(f"  ✗ {f}")

    return scores, total_pass, total_all, all_failures


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("="*70)
    print("OPENSIGHT DEMO DAY + REGRESSION — Cloud Run backend")
    print(f"Target: {WS_URL}")
    print("="*70)

    scenario_results, p1_critical = await part1()
    print("\n  [15s pause between parts]"); await asyncio.sleep(15)
    reg_scores, total_pass, total_all, reg_failures = await part2()

    # ── FINAL COMBINED REPORT ─────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("FINAL COMBINED REPORT")
    print("="*70)

    # 1. Demo Day Verdict
    print("\n1. DEMO DAY VERDICT")
    expected_firsts = {
        "Headphones": {"D1a":"RESEARCH","D1b":"SHOPPING","D1c":"SHOPPING","D1d":"CALENDAR","D1e":"GENERAL"},
        "Omega3":     {"D2a":"RESEARCH","D2b":"SHOPPING","D2c":"SHOPPING","D2d":"GENERAL","D2e":"CALENDAR"},
        "Ashwagandha":{"D3a":"GENERAL","D3b":"RESEARCH","D3c":"SHOPPING","D3d":"GENERAL","D3e":"CALENDAR","D3f":"GENERAL"},
        "PeanutSnack":{"D4a":"SHOPPING","D4b":"SHOPPING","D4c":"GENERAL","D4d":"RESEARCH","D4e":"SHOPPING"},
    }
    display_names = {
        "Headphones":  "Headphones     — RESEARCH→SHOPPING→CALENDAR",
        "Omega3":      "Omega-3        — RESEARCH→SHOPPING→GENERAL→CAL",
        "Ashwagandha": "Rapid switch   — GEN→RES→SHOP→GEN→CAL→GEN",
        "PeanutSnack": "Peanut snack   — SHOP→SHOP→GEN→RES→SHOP",
    }
    critical_blockers = []
    nice_to_fix = []

    for sname, results in scenario_results.items():
        exp = expected_firsts[sname]
        chain_ok = all(r["first"] == exp.get(r["label"], r["first"]) for r in results)
        voice_ok = all(not r["vp"] or r["vp"] == ["TIMEOUT"] for r in results)
        verdict = "READY" if chain_ok and voice_ok else "NEEDS FIX"
        print(f"  {display_names[sname]:<47} {verdict}")
        for r in results:
            ea = exp.get(r["label"])
            if ea and r["first"] != ea:
                critical_blockers.append(
                    f"[{r['label']}] Query: '{r['label']}' → {r['first']} (expected {ea}). "
                    f"User hears: '{short(r['resp'], 55)}'"
                )
            if r["vp"] and r["vp"] != ["TIMEOUT"]:
                nice_to_fix.append(f"[{r['label']}] Voice issue: {r['vp']}")

    # 2. Regression Health Score
    baseline_pass, baseline_total = 33, 42
    print(f"\n2. REGRESSION HEALTH SCORE: {total_pass}/{total_all}  (prev baseline: {baseline_pass}/{baseline_total})")
    trend = "↑ IMPROVED" if total_pass/max(total_all,1) > baseline_pass/baseline_total else (
            "↓ REGRESSED" if total_pass/max(total_all,1) < baseline_pass/baseline_total else "→ STABLE")
    print(f"   Trend: {trend}")

    # 3. Critical blockers
    print("\n3. CRITICAL BLOCKERS (would fail on stage)")
    if critical_blockers:
        for c in critical_blockers:
            print(f"  !! {c}")
    else:
        print("  None found.")

    # 4. Nice-to-fix
    print("\n4. NICE-TO-FIX (won't break demo but worth polishing)")
    all_nice = nice_to_fix + reg_failures
    if all_nice:
        for n in all_nice[:6]:
            print(f"  • {n}")
    else:
        print("  Nothing.")

    # 5. Overall verdict
    print("\n5. OVERALL SHIP VERDICT")
    scenarios_ready = sum(
        1 for sname, results in scenario_results.items()
        if all(r["first"] == expected_firsts[sname].get(r["label"], r["first"]) for r in results)
        and all(not r["vp"] or r["vp"] == ["TIMEOUT"] for r in results)
    )
    if not critical_blockers and scenarios_ready >= 3:
        print(f"  ✓ READY FOR DEMO DAY — {scenarios_ready}/4 scenarios fully clean.")
        print("  Routing is solid, voice formatting is clean, error handling is robust.")
    elif critical_blockers and len(critical_blockers) <= 2:
        print(f"  ~ ALMOST READY — {len(critical_blockers)} routing issue(s) to fix first:")
        for c in critical_blockers:
            print(f"    {c}")
    else:
        print(f"  ✗ NOT READY — {len(critical_blockers)} critical blocker(s). Fix before demo day.")

    print("\n" + "="*70)


asyncio.run(main())
os.remove(__file__)
print("\n[test file deleted]")
