from playwright.sync_api import sync_playwright
import asyncio

def _run_shopping_sync(query: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

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

                results.append(f"{title}, {price}, rated {rating}")
            except:
                continue

        browser.close()

        if not results:
         return f"I couldn't find results for {query} on Amazon."

        lines = []
        for i, r in enumerate(results, 1):
            # r is "title, price, rated X stars" — just grab title and price
            parts = r.split(", ")
            title = parts[0][:60]  # truncate long titles
            price = parts[1] if len(parts) > 1 else ""
            lines.append(f"Option {i}: {title}, {price}")

        return " ".join(lines)

async def run_shopping_agent(query: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_shopping_sync, query)