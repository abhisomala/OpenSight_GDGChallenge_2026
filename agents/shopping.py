import asyncio
import re
import threading
import time
from typing import Optional
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


def _is_followup_query(query: str) -> bool:
    text = (query or "").lower()
    markers = [
        r"\boption\s*\d+\b",
        r"\b(first|second|third|1st|2nd|3rd)\b",
        r"\b(click|open|buy|select|choose)\b",
        r"\b(that one|this one|the first one|the second one|the third one)\b",
        r"\btell me more\b",
        r"\bmore about\b",
        r"\brepeat\b",
    ]
    return any(re.search(pattern, text) for pattern in markers)


def _is_open_intent(query: str) -> bool:
    return bool(re.search(r'\b(click|open|buy|select|choose)\b', query or "", re.IGNORECASE))


def _extract_option_index(query: str, max_options: int) -> Optional[int]:
    if max_options <= 0:
        return None

    text = (query or "").lower()

    number_match = re.search(r'\boption\s*(\d+)\b', text)
    if number_match:
        idx = int(number_match.group(1)) - 1
        return idx if 0 <= idx < max_options else None

    ordinal_map = {
        "first": 0,
        "1st": 0,
        "one": 0,
        "second": 1,
        "2nd": 1,
        "two": 1,
        "third": 2,
        "3rd": 2,
        "three": 2,
    }
    for word, idx in ordinal_map.items():
        if re.search(rf'\b{re.escape(word)}\b', text):
            return idx if idx < max_options else None

    return None


def _open_product_page(url: str) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=680,780",
                "--window-position=720,60",
            ])
            context = browser.new_context(viewport={"width": 680, "height": 780})
            page = context.new_page()
            page.goto(url)
            page.wait_for_load_state("domcontentloaded")
            # Keep it open briefly so the user can see the page.
            page.wait_for_timeout(15000)
            browser.close()
    except Exception as e:
        print(f"[shopping] open page error: {e}")


def _handle_followup_query(query: str, shopping_memory: dict) -> str:
    results = shopping_memory.get("last_results") or []
    if not results:
        return "I don't have recent shopping options yet. Ask me to search Amazon first."

    idx = _extract_option_index(query, len(results))
    text = (query or "").lower()

    if "repeat" in text and "option" in text:
        parts = [f"Option {i + 1}: {r['title']}, {r['price']}" for i, r in enumerate(results)]
        return "Here are the options again. " + ". ".join(parts) + "."

    if idx is None:
        if len(results) == 1:
            idx = 0
        else:
            return "I can do that. Which option number do you want?"

    selected = results[idx]
    if _is_open_intent(query):
        if selected.get("url"):
            threading.Thread(target=_open_product_page, args=(selected["url"],), daemon=True).start()
            return f"Opening option {idx + 1}: {selected['title']} at {selected['price']}."
        return f"I found option {idx + 1}, {selected['title']} at {selected['price']}, but I could not open its product link."

    return f"Option {idx + 1} is {selected['title']} at {selected['price']}. Want me to open it?"


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

                    title_link_el = item.query_selector('h2 a')
                    href = title_link_el.get_attribute('href') if title_link_el else None
                    product_url = f"https://www.amazon.com{href}" if href and href.startswith('/') else href

                    results.append({
                        "title": title[:55],
                        "price": price,
                        "price_val": _parse_price(price),
                        "url": product_url,
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


async def run_shopping_agent(query: str, shopping_memory: dict | None = None) -> tuple[str, dict]:
    shopping_memory = shopping_memory or {"last_query": "", "last_results": []}

    if _is_followup_query(query) and shopping_memory.get("last_results"):
        return _handle_followup_query(query, shopping_memory), shopping_memory

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
        return f"I searched Amazon but couldn't find results for {query}.", shopping_memory

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
            ), {
                "last_query": _clean_query(query),
                "last_results": [
                    {
                        "title": cheapest["title"],
                        "price": cheapest["price"],
                        "url": cheapest.get("url"),
                    }
                ],
            }
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
    memory_update = {
        "last_query": _clean_query(query),
        "last_results": [
            {
                "title": r["title"],
                "price": r["price"],
                "url": r.get("url"),
            }
            for r in results
        ],
    }
    return response, memory_update