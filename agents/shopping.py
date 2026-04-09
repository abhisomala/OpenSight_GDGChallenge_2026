import asyncio
import re
import threading
import time
from playwright.sync_api import sync_playwright


def _clean_query(query: str) -> str:
    cleaned = re.sub(r'\s*(on amazon|from amazon|at amazon|amazon)\s*', ' ', query, flags=re.IGNORECASE)
    return cleaned.strip()


def _extract_budget(query: str):
    match = re.search(r'\$(\d+)', query)
    if match:
        return float(match.group(1))
    match = re.search(r'under\s+(\d+)|less\s+than\s+(\d+)|below\s+(\d+)', query, re.IGNORECASE)
    if match:
        val = match.group(1) or match.group(2) or match.group(3)
        return float(val)
    return None


def _parse_price(text: str):
    match = re.search(r'\$([\d,]+\.?\d*)', text)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def _open_amazon_browser(query: str, result_holder: dict) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=680,780",
                "--window-position=720,60",
            ])
            context = browser.new_context(viewport={"width": 680, "height": 780})
            page = context.new_page()

            page.goto("https://www.amazon.com")
            page.wait_for_load_state("domcontentloaded")

            clean = _clean_query(query)
            print(f"[shopping] searching Amazon for: {clean}")
            page.fill('#twotabsearchtextbox', clean)
            page.press('#twotabsearchtextbox', 'Enter')
            page.wait_for_load_state("domcontentloaded")

            results = []
            items = page.query_selector_all('[data-component-type="s-search-result"]')

            for item in items[:8]:
                try:
                    title_el = item.query_selector('h2 span')
                    price_el = item.query_selector('.a-price .a-offscreen')

                    title = title_el.inner_text() if title_el else "Unknown"
                    price = price_el.inner_text() if price_el else ""

                    title_lower = title.lower()
                    if any(skip in title_lower for skip in ["case", "cover", "screen protector", "keyboard cover", "sleeve", "bag"]):
                        continue

                    if not price:
                        continue

                    results.append({
                        "title": title[:55],
                        "price": price,
                        "price_val": _parse_price(price),
                    })
                except Exception:
                    continue

            result_holder["results"] = results
            result_holder["done"] = True

            while not result_holder.get("close"):
                page.wait_for_timeout(500)

            browser.close()
    except Exception as e:
        print(f"[shopping] browser error: {e}")
        result_holder["done"] = True
        result_holder["results"] = []


def _wait_for_done(result_holder: dict) -> None:
    while not result_holder.get("done"):
        time.sleep(0.2)


async def run_shopping_agent(query: str) -> str:
    result_holder = {"done": False, "results": [], "close": False}

    thread = threading.Thread(
        target=_open_amazon_browser,
        args=(query, result_holder),
        daemon=True,
    )
    thread.start()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _wait_for_done(result_holder))

    results = result_holder.get("results", [])

    if not results:
        result_holder["close"] = True
        return f"I searched Amazon but couldn't find results for {query}."

    # filter by budget if one was specified
    budget = _extract_budget(query)
    if budget:
        in_budget = [r for r in results if r["price_val"] and r["price_val"] <= budget]
        if in_budget:
            results = in_budget[:3]
        else:
            cheapest = min(results, key=lambda r: r["price_val"] or 9999)
            result_holder["close"] = True
            return (
                f"I couldn't find anything under ${int(budget)}. "
                f"The cheapest I found was the {cheapest['title']} at {cheapest['price']}."
            )
    else:
        results = results[:3]

    # build natural spoken response
    if len(results) == 1:
        r = results[0]
        response = f"I found one option — {r['title']} for {r['price']}."
    else:
        parts = [f"Option {i+1}: {r['title']}, {r['price']}" for i, r in enumerate(results)]
        response = "Here's what I found. " + ". ".join(parts) + "."

    def delayed_close():
        time.sleep(12)
        result_holder["close"] = True

    threading.Thread(target=delayed_close, daemon=True).start()
    return response