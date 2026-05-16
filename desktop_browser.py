"""Local Playwright browser execution for OpenSight desktop client.

Dispatched from agent.py when server sends a browser_action message.
All functions are synchronous and meant to be called via asyncio.to_thread().
"""

import re
import threading
import time
from typing import Optional

from playwright.sync_api import sync_playwright
import browser_manager


# ── Amazon helpers (mirrored from agents/shopping.py) ────────────────────────
# Duplicated here so desktop_browser.py is self-contained and importable on the
# client without pulling in server-side agent dependencies.

def _scrape_product_details(page) -> dict:
    details = {"title": "", "ingredients": "", "bullets": [], "url": page.url}
    try:
        el = page.query_selector("#productTitle")
        if el:
            details["title"] = el.inner_text().strip()
    except Exception:
        pass

    ingredient_selectors = [
        "#ingredient-statement",
        "#important-information .a-section p",
        "[data-feature-name='ingredientStatement'] span",
        "#ingredients-content",
        ".ingredient-statement",
        "#tech-specs-content tr:has-text('Ingredients') td",
    ]
    for sel in ingredient_selectors:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 20:
                    details["ingredients"] = text
                    break
        except Exception:
            continue

    if not details["ingredients"]:
        try:
            important = page.query_selector("#important-information")
            if important:
                text = important.inner_text().strip()
                match = re.search(r'ingredients[:\s]+(.+?)(\n\n|$)', text, re.IGNORECASE | re.DOTALL)
                if match:
                    details["ingredients"] = match.group(1).strip()[:600]
        except Exception:
            pass

    try:
        bullet_els = page.query_selector_all("#feature-bullets li span.a-list-item")
        details["bullets"] = [
            el.inner_text().strip() for el in bullet_els
            if el.inner_text().strip()
        ][:8]
    except Exception:
        pass

    return details


def _clean_query(query: str) -> str:
    cleaned = re.sub(r'\s*(on amazon|from amazon|at amazon|amazon)\s*', ' ', query, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\[context:[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _parse_price(text: str):
    match = re.search(r'\$([\d,]+\.?\d*)', text)
    if match:
        return float(match.group(1).replace(',', ''))
    return None


def _should_skip_result(title: str, query: str) -> bool:
    title_lower = title.lower()
    query_lower = query.lower()

    universal_skip = ["screen protector", "keyboard cover", "sleeve", "bag"]
    if any(s in title_lower for s in universal_skip):
        return True

    supplement_query = any(w in query_lower for w in [
        "supplement", "vitamin", "pill", "capsule", "tablet", "powder",
        "oil", "fish oil", "protein", "omega", "probiotic", "collagen",
    ])
    electronics_noise = ["case", "cover", "stand", "mount", "charger", "cable", "adapter"]
    if not supplement_query and any(s in title_lower for s in electronics_noise):
        return True

    if supplement_query:
        supplement_skip = [
            "empty bottle", "empty capsule", "pill cutter", "pill organizer",
            "pill splitter", "pill crusher", "label", "labeling", "sticker",
            "bottle brush", "storage case", "weekly", "travel case",
        ]
        if any(s in title_lower for s in supplement_skip):
            return True

    return False


def _build_product_url(href: Optional[str], asin: Optional[str] = None) -> Optional[str]:
    if asin:
        return f"https://www.amazon.com/dp/{asin}"
    if not href:
        return None
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', href)
    if asin_match:
        return f"https://www.amazon.com/dp/{asin_match.group(1)}"
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://www.amazon.com{href}"
    return f"https://www.amazon.com/{href}"


_CHROMIUM_ARGS = [
    "--window-size=720,900",
    "--window-position=720,0",
    "--no-first-run",
    "--no-default-browser-check",
]


# ── Amazon ────────────────────────────────────────────────────────────────────

def run_amazon_search(query: str) -> dict:
    """Open Amazon, search, scrape up to 8 results. Browser stays open. Blocks until results ready."""
    result_holder: dict = {"done": False, "results": [], "close": False}

    def _run():
        def _close():
            result_holder["close"] = True

        try:
            pre_launch = browser_manager.snapshot_chromium_hwnds()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, args=_CHROMIUM_ARGS)
                context = browser.new_context(viewport={"width": 720, "height": 900})
                page = context.new_page()
                browser_manager.register(_close)

                page.goto("https://www.amazon.com")
                page.wait_for_load_state("domcontentloaded")

                clean = _clean_query(query)
                page.fill('#twotabsearchtextbox', clean)
                page.press('#twotabsearchtextbox', 'Enter')
                page.wait_for_load_state("domcontentloaded")

                hwnd = browser_manager._find_chromium_hwnd(timeout=6.0, seen_before=pre_launch)
                if hwnd:
                    browser_manager.set_browser_hwnd(hwnd)
                    browser_manager.focus_browser()

                results = []
                items = page.query_selector_all('[data-component-type="s-search-result"]')
                for item in items[:8]:
                    try:
                        title_el = item.query_selector('h2 span')
                        price_el = item.query_selector('.a-price .a-offscreen')
                        title = title_el.inner_text() if title_el else "Unknown"
                        price = price_el.inner_text() if price_el else ""
                        if _should_skip_result(title, query):
                            continue
                        if not price:
                            continue
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
        except Exception:
            print("[desktop_browser] Amazon search error")
            result_holder["done"] = True

    threading.Thread(target=_run, daemon=True).start()
    while not result_holder.get("done"):
        time.sleep(0.2)

    return {"results": result_holder.get("results", []), "scraped": {}}


def open_product_page(url: str) -> dict:
    """Open an Amazon product URL, scrape it, keep browser alive. Blocks until scraping done."""
    scraped: dict = {"title": "", "ingredients": "", "bullets": [], "url": ""}
    done_event = threading.Event()

    def _run():
        browser_manager.close_all()
        holder: dict = {"close": False}

        def _close():
            holder["close"] = True

        try:
            pre_launch = browser_manager.snapshot_chromium_hwnds()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, args=_CHROMIUM_ARGS)
                context = browser.new_context(viewport={"width": 720, "height": 900})
                page = context.new_page()
                browser_manager.register(_close)
                page.goto(url)
                page.wait_for_load_state("domcontentloaded")

                hwnd = browser_manager._find_chromium_hwnd(timeout=6.0, seen_before=pre_launch)
                if hwnd:
                    browser_manager.set_browser_hwnd(hwnd)
                    browser_manager.focus_browser()

                try:
                    page.wait_for_timeout(2000)
                    details = _scrape_product_details(page)
                    scraped.update(details)
                except Exception:
                    print("[desktop_browser] product scrape error")

                done_event.set()

                while not holder.get("close"):
                    page.wait_for_timeout(500)
                browser.close()
        except Exception:
            print("[desktop_browser] open product error")
            done_event.set()

    threading.Thread(target=_run, daemon=True).start()
    done_event.wait(timeout=30)
    return {"scraped": scraped}


# ── Scholar ───────────────────────────────────────────────────────────────────

def open_scholar_browser(url: str) -> dict:
    """Open Google Scholar at url and keep browser alive. Blocks until visible."""
    opened_event = threading.Event()

    def _run():
        browser_manager.close_all()
        holder: dict = {"close": False}

        def _close():
            holder["close"] = True

        try:
            pre_launch = browser_manager.snapshot_chromium_hwnds()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, args=_CHROMIUM_ARGS)
                context = browser.new_context(viewport={"width": 720, "height": 900})
                page = context.new_page()
                browser_manager.register(_close)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass

                hwnd = browser_manager._find_chromium_hwnd(timeout=6.0, seen_before=pre_launch)
                if hwnd:
                    browser_manager.set_browser_hwnd(hwnd)
                    browser_manager.focus_browser()

                opened_event.set()

                while not holder.get("close"):
                    page.wait_for_timeout(500)
                browser.close()
        except Exception:
            print("[desktop_browser] Scholar browser error")
            opened_event.set()

    threading.Thread(target=_run, daemon=True).start()
    opened_event.wait(timeout=20)
    return {"opened": True}


def open_paper_window(url: str) -> dict:
    """Open a research paper URL in a browser. Blocks until visible."""
    opened_event = threading.Event()

    def _run():
        browser_manager.close_all()
        holder: dict = {"close": False}

        def _close():
            holder["close"] = True

        try:
            pre_launch = browser_manager.snapshot_chromium_hwnds()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False, args=_CHROMIUM_ARGS)
                context = browser.new_context(
                    accept_downloads=True,
                    viewport={"width": 720, "height": 900},
                )
                page = context.new_page()
                browser_manager.register(_close)
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass

                hwnd = browser_manager._find_chromium_hwnd(timeout=6.0, seen_before=pre_launch)
                if hwnd:
                    browser_manager.set_browser_hwnd(hwnd)
                    browser_manager.focus_browser()

                opened_event.set()

                while not holder.get("close"):
                    page.wait_for_timeout(500)
                browser.close()
        except Exception:
            print("[desktop_browser] paper window error")
            opened_event.set()

    threading.Thread(target=_run, daemon=True).start()
    opened_event.wait(timeout=20)
    return {"opened": True}


# ── Dispatcher ────────────────────────────────────────────────────────────────

def dispatch(agent: str, query: Optional[str] = None, url: Optional[str] = None) -> dict:
    """Route a browser_action to the correct Playwright function. Called via asyncio.to_thread."""
    if agent == "SHOPPING":
        return run_amazon_search(query or "")
    if agent == "SHOPPING_OPEN":
        return open_product_page(url or "")
    if agent == "RESEARCH":
        return open_scholar_browser(url or "")
    if agent == "RESEARCH_OPEN":
        return open_paper_window(url or "")
    return {}
