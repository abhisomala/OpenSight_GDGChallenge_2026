"""OpenSight behavioral evaluation — 19 test cases against Cloud Run backend."""
import asyncio
import json
import time
import websockets

WS_URL = "wss://opensight-backend-348346331222.us-east1.run.app/ws"

# ── Mock data for shopping browser_result responses ──────────────────────────

OMEGA3_RESULTS = {
    "results": [
        {"title": "Nature Made Fish Oil 1200mg Omega-3", "price": "$12.99", "price_val": 12.99, "url": "https://www.amazon.com/dp/B001XYZ001"},
        {"title": "Nordic Naturals Omega-3 Fish Oil", "price": "$24.99", "price_val": 24.99, "url": "https://www.amazon.com/dp/B001XYZ002"},
        {"title": "Viva Naturals Triple Strength Omega-3", "price": "$27.99", "price_val": 27.99, "url": "https://www.amazon.com/dp/B001XYZ003"},
    ],
    "scraped": {},
}

LAPTOP_RESULTS = {
    "results": [
        {"title": "Acer Aspire 5 Slim Laptop 15.6 inch", "price": "$549.99", "price_val": 549.99, "url": "https://www.amazon.com/dp/B002XYZ001"},
        {"title": "ASUS VivoBook 15 Thin and Light", "price": "$699.99", "price_val": 699.99, "url": "https://www.amazon.com/dp/B002XYZ002"},
        {"title": "HP Pavilion 15 Laptop Intel Core i5", "price": "$749.99", "price_val": 749.99, "url": "https://www.amazon.com/dp/B002XYZ003"},
    ],
    "scraped": {},
}

PRODUCT_SCRAPE = {
    "scraped": {
        "title": "Nordic Naturals Omega-3 Fish Oil",
        "ingredients": (
            "Fish Oil Concentrate (from Anchovy and Sardine), Gelatin (bovine), "
            "Water, Glycerin, Natural Lemon Flavor. "
            "Contains: Fish (Anchovy, Sardine)."
        ),
        "bullets": [
            "1280mg Omega-3 per serving",
            "650mg EPA and 450mg DHA",
            "Purified to remove PCBs and mercury",
            "No artificial flavors or colors",
        ],
        "url": "https://www.amazon.com/dp/B001XYZ002",
    }
}


def _mock_for_test(test_num: int, agent_name: str) -> dict:
    """Return appropriate mock browser_result data for the given test."""
    if agent_name == "SHOPPING_OPEN":
        return PRODUCT_SCRAPE
    if agent_name == "SHOPPING":
        if test_num == 12:
            return LAPTOP_RESULTS
        return OMEGA3_RESULTS
    return {}


async def run_query(text: str, test_num: int, timeout: int = 45) -> dict:
    """Send one query, handle browser_action mocks, return full message log."""
    statuses = []
    browser_actions = []
    research_statuses = []
    response_text = ""
    error = None

    try:
        async with websockets.connect(WS_URL, open_timeout=10) as ws:
            await ws.send(json.dumps({"text": text}))

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 30))
                except asyncio.TimeoutError:
                    error = "TIMEOUT waiting for response"
                    break

                msg = json.loads(raw)
                mtype = msg.get("type")

                if mtype == "status":
                    agent = msg.get("agent", "")
                    detail = msg.get("detail", "")
                    state = msg.get("state", "")
                    if state != "idle":
                        statuses.append(f"{agent} -> {detail or state}")

                elif mtype == "research_status":
                    research_statuses.append(msg.get("text", ""))

                elif mtype == "browser_action":
                    agent_name = msg.get("agent", "")
                    browser_actions.append(agent_name)
                    # Server blocks on SHOPPING / SHOPPING_OPEN waiting for browser_result
                    if agent_name in ("SHOPPING", "SHOPPING_OPEN"):
                        mock = _mock_for_test(test_num, agent_name)
                        await ws.send(json.dumps({
                            "type": "browser_result",
                            "agent": agent_name,
                            "data": mock,
                        }))
                    # RESEARCH / RESEARCH_OPEN are fire-and-forget — no reply needed

                elif mtype == "response":
                    response_text = msg.get("text", "")
                    break

    except Exception as e:
        error = str(e)

    return {
        "statuses": statuses,
        "browser_actions": browser_actions,
        "research_statuses": research_statuses,
        "response": response_text,
        "error": error,
    }


# ── Test definitions ──────────────────────────────────────────────────────────

TESTS = [
    # (num, query, expected_agent, notes)
    (1,  "What is the capital of France?",                         "GENERAL",   'Must mention "Paris"'),
    (2,  "Who won the FIFA World Cup in 2022?",                    "GENERAL",   'Must say "Argentina"'),
    (3,  "What is two plus two?",                                  "GENERAL",   'Must say "four" or "4"'),
    (4,  "Tell me a joke",                                         "GENERAL",   "Must be an actual joke"),
    (5,  "Find me research on omega-3 and brain health",           "RESEARCH",  "Paper titles, no Amazon mention"),
    (6,  "Who wrote the first paper?",                             "RESEARCH",  "Author name, not 'I don't know'"),
    (7,  "Tell me more about the findings",                        "RESEARCH",  "Relevant findings summary"),
    (8,  "Open the first one",                                     "RESEARCH",  "Must NOT go to Amazon"),
    (9,  "Find me a supplement for that under $30",                "SHOPPING",  "Must mention omega-3/fish oil, price ≤$30"),
    (10, "Open the second one",                                    "SHOPPING",  "Open product, not search again"),
    (11, "What are the ingredients?",                              "GENERAL",   "Specific ingredients from scrape"),
    (12, "Find me a laptop under $800",                            "SHOPPING",  "Laptops with prices ≤$800"),
    (13, "Repeat the options",                                     "SHOPPING",  "Lists same laptop options again"),
    (14, "Tell me more about the first one",                       "SHOPPING",  "Details on first laptop"),
    (15, "Find me papers on vitamin D",                            "RESEARCH",  "Must NOT go to shopping"),
    (16, "Open it",                                                "RESEARCH",  "Asks which one, not an error"),
    (17, "the",                                                    "NONE",      "Garble — 'I didn't catch that'"),
    (18, "Yes",                                                    "GENERAL",   "Graceful, no crash"),
    (19, "What is the capital of Germany?",                        "GENERAL",   "Must say 'Berlin', no prior context bleed"),
]


def _infer_routed_agent(statuses: list, browser_actions: list) -> str:
    """Infer the primary routed agent from status messages."""
    for s in statuses:
        upper = s.upper()
        if "SHOPPING" in upper:
            return "SHOPPING"
        if "RESEARCH" in upper:
            return "RESEARCH"
        if "CALENDAR" in upper:
            return "CALENDAR"
        if "GENERAL" in upper or "THINKING" in upper or "thinking" in s.lower():
            return "GENERAL"
    if browser_actions:
        for ba in browser_actions:
            if "SHOPPING" in ba:
                return "SHOPPING"
            if "RESEARCH" in ba:
                return "RESEARCH"
    return "NONE"


def _check_pass(num: int, expected_agent: str, routed_agent: str,
                response: str, browser_actions: list) -> tuple[bool, list[str]]:
    """Return (passed, [failure reasons])."""
    failures = []
    resp_lower = response.lower()

    # Agent routing check
    if expected_agent == "NONE":
        # Garbled — must not route to any agent, must be catch phrase
        if "i didn't catch that" not in resp_lower and "could you say that again" not in resp_lower:
            failures.append(f"Garbled not caught — got response: '{response[:80]}'")
    elif routed_agent != expected_agent:
        failures.append(f"Routed to {routed_agent}, expected {expected_agent}")

    # Response content checks per test
    if num == 1:
        if "paris" not in resp_lower:
            failures.append("'Paris' not mentioned")
    elif num == 2:
        if "argentina" not in resp_lower:
            failures.append("'Argentina' not mentioned")
    elif num == 3:
        if "four" not in resp_lower and "4" not in resp_lower:
            failures.append("Answer '4' or 'four' not found")
    elif num == 4:
        if len(response) < 20 or "sorry" in resp_lower or "can't" in resp_lower:
            failures.append("Did not produce a joke")
    elif num == 5:
        if "amazon" in resp_lower or "supplement" in resp_lower:
            failures.append("Response mentions Amazon or supplement (should be research only)")
        if not any(w in resp_lower for w in ["paper", "study", "research", "found", "published"]):
            failures.append("No mention of research papers in response")
    elif num == 6:
        low = resp_lower
        if "i don't know" in low or "i don't have" in low or "no information" in low:
            failures.append("Response said it doesn't know the author")
        if "paper" not in low and "author" not in low and "wrote" not in low and len(response) < 15:
            failures.append("Response too short / no author info")
    elif num == 7:
        if len(response) < 20:
            failures.append("Response too short for findings summary")
        if "paper" not in resp_lower and "omega" not in resp_lower and "brain" not in resp_lower \
                and "health" not in resp_lower and "study" not in resp_lower and "finding" not in resp_lower:
            failures.append("Response doesn't mention relevant research content")
    elif num == 8:
        # Must NOT route to shopping; must say "opening" or ask which one
        if routed_agent == "SHOPPING":
            failures.append("CRITICAL: Routed to SHOPPING instead of RESEARCH")
        if not any(w in resp_lower for w in ["opening", "which one", "first", "paper", "don't have"]):
            failures.append("Response doesn't confirm opening or clarify")
        if "amazon" in resp_lower:
            failures.append("Response mentions Amazon (wrong agent)")
    elif num == 9:
        if not any(w in resp_lower for w in ["omega", "fish oil", "omega-3", "omega 3"]):
            failures.append("Cross-agent handoff failed — no omega-3/fish oil in response")
        # Check price constraint respected
        if "$30" in response or "30" in response:
            pass  # price mentioned — good
    elif num == 10:
        if "open" not in resp_lower and "opening" not in resp_lower:
            failures.append("Response doesn't say 'opening'")
        if "SHOPPING_OPEN" not in browser_actions:
            failures.append("No SHOPPING_OPEN browser_action sent")
    elif num == 11:
        if "i don't" in resp_lower or "no information" in resp_lower or "not sure" in resp_lower:
            failures.append("Didn't answer from scraped data")
        if not any(w in resp_lower for w in ["ingredient", "fish", "oil", "anchovy", "gelatin",
                                              "glycerin", "lemon", "omega", "epa", "dha"]):
            failures.append("No ingredient info in response (scrape not used)")
    elif num == 12:
        if not any(w in resp_lower for w in ["laptop", "acer", "asus", "hp", "pavilion", "vivobook"]):
            failures.append("No laptop names in response")
        if "SHOPPING" not in browser_actions:
            failures.append("No SHOPPING browser_action for new laptop search")
    elif num == 13:
        if not any(w in resp_lower for w in ["acer", "asus", "hp", "laptop"]):
            failures.append("Repeat didn't include laptop options")
    elif num == 14:
        if len(response) < 10:
            failures.append("Response too short for product detail")
    elif num == 15:
        if routed_agent == "SHOPPING":
            failures.append("CRITICAL: 'Find me papers on vitamin D' routed to SHOPPING")
        if not any(w in resp_lower for w in ["paper", "study", "vitamin d", "vitamin", "research", "found"]):
            failures.append("No research content in response")
    elif num == 16:
        if "which" not in resp_lower and "first" not in resp_lower and "second" not in resp_lower \
                and "don't have" not in resp_lower:
            failures.append("Ambiguous 'open it' not handled — no clarification asked")
    elif num == 17:
        if "i didn't catch that" not in resp_lower and "say that again" not in resp_lower:
            failures.append(f"Garble not caught — got: '{response[:60]}'")
    elif num == 18:
        if not response or len(response) < 3:
            failures.append("Empty or very short response for 'Yes'")
    elif num == 19:
        if "berlin" not in resp_lower:
            failures.append("'Berlin' not in response")
        # Should not bleed prior context
        if "omega" in resp_lower or "supplement" in resp_lower or "paper" in resp_lower:
            failures.append("Prior context bled into unrelated query")

    if not response and expected_agent != "NONE":
        failures.append("Empty response (timeout or error?)")

    return len(failures) == 0, failures


async def main():
    results = []
    print(f"\n{'='*70}")
    print(f"  OpenSight Behavioral Evaluation — {len(TESTS)} test cases")
    print(f"  Backend: {WS_URL}")
    print(f"{'='*70}\n")

    for num, query, expected_agent, notes in TESTS:
        print(f"[{num:02d}] {query}")
        r = await run_query(query, num)
        routed = _infer_routed_agent(r["statuses"], r["browser_actions"])
        passed, failures = _check_pass(num, expected_agent, routed, r["response"], r["browser_actions"])

        verdict = "PASS" if passed else "FAIL"
        print(f"     ROUTING : {' | '.join(r['statuses']) or '(none)'}")
        if r["browser_actions"]:
            print(f"     BROWSER : {r['browser_actions']}")
        print(f"     RESPONSE: {r['response'][:200] or '(empty)'}")
        if r["error"]:
            print(f"     ERROR   : {r['error']}")
        print(f"     VERDICT : {verdict}")
        if failures:
            for f in failures:
                print(f"     ISSUE   : {f}")
        print()

        results.append({
            "num": num,
            "query": query,
            "expected_agent": expected_agent,
            "routed_agent": routed,
            "response": r["response"],
            "browser_actions": r["browser_actions"],
            "passed": passed,
            "failures": failures,
            "notes": notes,
        })

        # Brief pause between tests to avoid hammering the server
        await asyncio.sleep(1.5)

    # ── Summary ───────────────────────────────────────────────────────────────
    passed_count = sum(1 for r in results if r["passed"])
    failed = [r for r in results if not r["passed"]]

    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed_count}/{len(TESTS)} passed")
    print(f"{'='*70}\n")

    if failed:
        print("FAILED TESTS:")
        for r in failed:
            print(f"\n  [{r['num']:02d}] {r['query']}")
            print(f"       Expected: {r['expected_agent']}  Got: {r['routed_agent']}")
            for f in r["failures"]:
                print(f"       - {f}")

    # ── Routing summary ───────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("  ROUTING TABLE")
    print(f"{'='*70}")
    for r in results:
        mark = "OK" if r["passed"] else "XX"
        print(f"  {mark} [{r['num']:02d}] {r['expected_agent']:10s} -> {r['routed_agent']:10s}  {r['query'][:55]}")

    print(f"\n{'='*70}")
    print(f"  PASS RATE: {passed_count}/{len(TESTS)} ({100*passed_count//len(TESTS)}%)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
