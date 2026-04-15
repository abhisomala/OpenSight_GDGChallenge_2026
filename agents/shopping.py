import asyncio
import re
import threading
import time
from typing import Optional
from urllib.parse import quote_plus
from playwright.sync_api import sync_playwright

_active_browser: dict | None = None


def close_active_browser():
    global _active_browser
    if _active_browser:
        _active_browser["close"] = True
        _active_browser = None


def _clean_query(query: str) -> str:
    cleaned = re.sub(r'\s*(on amazon|from amazon|at amazon|amazon)\s*', ' ', query, flags=re.IGNORECASE)
    return cleaned.strip()


def _shorten_title(title: str) -> str:
    title = re.split(r',|-|\|', title)[0].strip()
    if len(title) > 30:
        title = title[:30].rsplit(' ', 1)[0]
    return title


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
        "first": 0, "1st": 0, "one": 0,
        "second": 1, "2nd": 1, "two": 1,
        "third": 2, "3rd": 2, "three": 2,
    }
    for word, idx in ordinal_map.items():
        if re.search(rf'\b{re.escape(word)}\b', text):
            return idx if idx < max_options else None

    return None


def _build_product_url(href: str | None, asin: str | None = None) -> str | None:
    # prefer ASIN-based URL — always works, never redirects or errors
    if asin:
        return f"https://www.amazon.com/dp/{asin}"
    if not href:
        return None
    # try extracting ASIN from href as fallback
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', href)
    if asin_match:
        return f"https://www.amazon.com/dp/{asin_match.group(1)}"
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://www.amazon.com{href}"
    return f"https://www.amazon.com/{href}"


def _open_product_page(url: str) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            context = browser.new_context(viewport={"width": 720, "height": 900})
            page = context.new_page()
            page.goto(url)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(15000)
            browser.close()
    except Exception as e:
        print(f"[shopping] open page error: {e}")


def _handle_followup_query(query: str, shopping_memory: dict) -> str:
    results = shopping_memory.get("last_results") or []
    if not results:
        return "I don't have any options saved yet. Want me to search Amazon?"

    idx = _extract_option_index(query, len(results))
    text = (query or "").lower()

    if "repeat" in text:
        parts = [f"{i+1}: {_shorten_title(r['title'])} for {r['price']}" for i, r in enumerate(results)]
        return " ".join(parts)

    if idx is None:
        return "Which one — the first, second, or third?"

    selected = results[idx]

    if _is_open_intent(query):
        url = selected.get("url")
        title = _shorten_title(selected["title"])
        if not url:
            # properly encoded search fallback
            url = f"https://www.amazon.com/s?k={quote_plus(selected['title'])}"
        threading.Thread(target=_open_product_page, args=(url,), daemon=True).start()
        return f"Opening the {title} now."

    return f"That's the {_shorten_title(selected['title'])}, going for {selected['price']}. Want me to open it?"


def _open_amazon_browser(query: str, result_holder: dict) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=720,900",
                "--window-position=720,0",
                "--no-first-run",
                "--no-default-browser-check",
            ])
            context = browser.new_context(viewport={"width": 720, "height": 900})
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
                    if any(skip in title_lower for skip in [
                        "case", "cover", "screen protector", "keyboard cover", "sleeve", "bag"
                    ]):
                        continue

                    if not price:
                        continue

                    # grab ASIN directly from the card attribute — most reliable source
                    asin = item.get_attribute('data-asin')
                    title_link_el = item.query_selector('h2 a')
                    href = title_link_el.get_attribute('href') if title_link_el else None
                    product_url = _build_product_url(href, asin)

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


def _build_response(results: list) -> str:
    if len(results) == 1:
        r = results[0]
        return f"I found one — {_shorten_title(r['title'])} for {r['price']}."
    elif len(results) == 2:
        return (
            f"Two options. "
            f"{_shorten_title(results[0]['title'])} at {results[0]['price']}, "
            f"or {_shorten_title(results[1]['title'])} at {results[1]['price']}. "
            f"Which one?"
        )
    else:
        return (
            f"Got three options. "
            f"{_shorten_title(results[0]['title'])} at {results[0]['price']}, "
            f"{_shorten_title(results[1]['title'])} at {results[1]['price']}, "
            f"or {_shorten_title(results[2]['title'])} at {results[2]['price']}. "
            f"Which one?"
        )


async def run_shopping_agent(query: str, shopping_memory: dict | None = None, memory=None) -> tuple[str, dict]:
    global _active_browser
    shopping_memory = shopping_memory or {"last_query": "", "last_results": []}

    if _is_followup_query(query) and shopping_memory.get("last_results"):
        response = _handle_followup_query(query, shopping_memory)
        if memory is not None:
            memory.set_result("shopping", response)
            memory.add_turn("assistant", response, agent="shopping")
        return response, shopping_memory

    close_active_browser()

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
        response = "I couldn't find anything for that. Try rephrasing?"
        if memory is not None:
            memory.set_result("shopping", response)
            memory.add_turn("assistant", response, agent="shopping")
        return response, shopping_memory

    budget = _extract_budget(query)
    if budget:
        in_budget = [r for r in results if r["price_val"] and r["price_val"] <= budget]
        if in_budget:
            results = in_budget[:3]
        else:
            cheapest = min(results, key=lambda r: r["price_val"] or 9999)
            result_holder["close"] = True
            response = (
                f"Nothing under ${int(budget)}, sorry. "
                f"Closest I found is the {_shorten_title(cheapest['title'])} at {cheapest['price']}."
            )
            memory_out = {
                "last_query": _clean_query(query),
                "last_results": [{"title": cheapest["title"], "price": cheapest["price"], "url": cheapest.get("url")}],
            }
            if memory is not None:
                memory.set_result("shopping", response)
                memory.add_turn("assistant", response, agent="shopping")
            return response, memory_out
    else:
        results = results[:3]

    _active_browser = result_holder

    memory_update = {
        "last_query": _clean_query(query),
        "last_results": [
            {"title": r["title"], "price": r["price"], "url": r.get("url")}
            for r in results
        ],
    }

    response = _build_response(results)
    if memory is not None:
        memory.set_result("shopping", response)
        memory.add_turn("assistant", response, agent="shopping")
    return response, memory_update