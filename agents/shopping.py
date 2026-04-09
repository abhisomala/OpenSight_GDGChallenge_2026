from playwright.sync_api import sync_playwright
import threading

def _open_amazon_browser(query: str, result_holder: dict) -> None:
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False, args=[
                "--window-size=700,800",
                "--window-position=700,100",
            ])
            context = browser.new_context(viewport={"width": 700, "height": 800})
            page = context.new_page()

            page.goto("https://www.amazon.com")
            page.wait_for_load_state("domcontentloaded")

            page.fill('#twotabsearchtextbox', query)
            page.press('#twotabsearchtextbox', 'Enter')
            page.wait_for_load_state("domcontentloaded")

            results = []
            items = page.query_selector_all('[data-component-type="s-search-result"]')

            for item in items[:3]:
                try:
                    title_el = item.query_selector('h2 span')
                    price_el = item.query_selector('.a-price .a-offscreen')
                    rating_el = item.query_selector('.a-icon-alt')

                    title = title_el.inner_text() if title_el else "Unknown"
                    price = price_el.inner_text() if price_el else "Price unavailable"
                    rating = rating_el.inner_text() if rating_el else "No rating"

                    results.append(f"{title[:60]}, {price}")
                except:
                    continue

            result_holder["results"] = results
            result_holder["done"] = True

            # stay open until close_event is set
            while not result_holder.get("close"):
                page.wait_for_timeout(500)

            browser.close()
    except Exception as e:
        print(f"[shopping] browser error: {e}")
        result_holder["done"] = True
        result_holder["results"] = []


async def run_shopping_agent(query: str) -> str:
    import asyncio

    result_holder = {"done": False, "results": [], "close": False}

    thread = threading.Thread(
        target=_open_amazon_browser,
        args=(query, result_holder),
        daemon=True
    )
    thread.start()

    # wait for browser to finish scraping
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: _wait_for_done(result_holder))

    results = result_holder.get("results", [])

    if not results:
        result_holder["close"] = True
        return f"I searched Amazon for {query} but couldn't find clear results. Try rephrasing."

    response = f"Here are the top {len(results)} results for {query} on Amazon. "
    for i, r in enumerate(results, 1):
        response += f"Option {i}: {r}. "

    # close browser after response is built — it'll stay open while TTS plays
    # caller closes it by setting close=True after speech
    # for now close after 10 seconds
    def delayed_close():
        import time
        time.sleep(10)
        result_holder["close"] = True

    threading.Thread(target=delayed_close, daemon=True).start()

    return response


def _wait_for_done(result_holder: dict) -> None:
    import time
    while not result_holder.get("done"):
        time.sleep(0.2)