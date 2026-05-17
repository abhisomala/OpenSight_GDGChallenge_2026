"""Amazon search result synthesis for the OpenSight server.

Playwright execution has moved to desktop_browser.py (runs on the desktop client).
This module handles server-side logic only: response synthesis, followup detection,
budget filtering, and reading/writing scraped product details for general.py.
"""

import re
from typing import Optional

_open_product_details: dict = {
    "title": "",
    "ingredients": "",
    "bullets": [],
    "url": "",
}


def get_open_product_details() -> dict:
    """Return the latest scraped product details (read by general.py)."""
    return _open_product_details


def set_open_product_details(details: dict) -> None:
    """Store scraped data received from a SHOPPING_OPEN browser_result."""
    _open_product_details.update(details)


def _clean_query(query: str) -> str:
    cleaned = re.sub(r'\s*(on amazon|from amazon|at amazon|amazon)\s*', ' ', query, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*\[context:[^\]]*\]', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _shorten_title(title: str) -> str:
    title = re.split(r',|-|\|', title)[0].strip()
    if len(title) > 45:
        title = title[:45].rsplit(' ', 1)[0]
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
    if any(w in text for w in ["find me", "search for", "look for", "can you find", "get me", "show me"]):
        return False
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
        "first": 0, "1st": 0,
        "second": 1, "2nd": 1,
        "third": 2, "3rd": 2,
    }
    for word, idx in ordinal_map.items():
        if re.search(rf'\b{re.escape(word)}\b', text):
            return idx if idx < max_options else None
    return None


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


def get_followup_product_url(query: str, shopping_memory: dict) -> Optional[str]:
    """Return the product URL for an open-intent followup, or None if can't determine."""
    results = shopping_memory.get("last_results") or []
    if not results:
        return None
    idx = _extract_option_index(query, len(results))
    if idx is None:
        return None
    return results[idx].get("url")


def get_followup_product_title(query: str, shopping_memory: dict) -> str:
    """Return the short product title for an open-intent followup."""
    results = shopping_memory.get("last_results") or []
    if not results:
        return "that"
    idx = _extract_option_index(query, len(results))
    if idx is None:
        return "that"
    return _shorten_title(results[idx].get("title", "that"))


def _handle_followup_query(query: str, shopping_memory: dict) -> str:
    """Handle text-only follow-ups (repeat, tell me more, ordinal without open intent).

    Open-intent follow-ups (open/click/buy) are handled in server.py via
    browser_action SHOPPING_OPEN before this function is ever called.
    """
    results = shopping_memory.get("last_results") or []
    if not results:
        return "I don't have any options saved yet. Want me to search Amazon?"

    idx = _extract_option_index(query, len(results))
    text = (query or "").lower()

    if "repeat" in text:
        parts = [f"Option {i+1}, {_shorten_title(r['title'])} at {r['price']}" for i, r in enumerate(results)]
        return ". ".join(parts) + "."

    if idx is None:
        return "Which one — the first, second, or third?"

    selected = results[idx]
    return f"That's the {_shorten_title(selected['title'])}, going for {selected['price']}. Want me to open it?"


def synthesize_shopping_response(
    browser_data: dict,
    query: str,
    shopping_mem: dict,
    memory=None,
) -> tuple[str, dict]:
    """Build a spoken response from Amazon search results received via browser_result.

    browser_data is the 'data' field of the SHOPPING browser_result message.
    Returns (response_text, memory_update).
    """
    results = browser_data.get("results", [])

    if browser_data.get("error"):
        response = "Shopping isn't available right now. Try running the app locally."
        if memory is not None:
            memory.add_turn("assistant", response, agent="shopping")
        return response, shopping_mem

    if not results:
        response = "I couldn't find anything for that. Try rephrasing?"
        if memory is not None:
            memory.set_result("shopping", response)
            memory.add_turn("assistant", response, agent="shopping")
        return response, shopping_mem

    budget = _extract_budget(query)
    if budget:
        in_budget = [r for r in results if r.get("price_val") and r["price_val"] <= budget]
        if in_budget:
            results = in_budget[:3]
        else:
            cheapest = min(results, key=lambda r: r.get("price_val") or 9999)
            response = (
                f"Nothing under ${int(budget)}, sorry. "
                f"Closest I found is the {_shorten_title(cheapest['title'])} at {cheapest['price']}."
            )
            memory_out = {
                "last_query": _clean_query(query),
                "last_results": [
                    {"title": cheapest["title"], "price": cheapest["price"], "url": cheapest.get("url")}
                ],
            }
            if memory is not None:
                memory.set_result("shopping", response)
                memory.add_turn("assistant", response, agent="shopping")
            return response, memory_out
    else:
        results = results[:3]

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


async def run_shopping_agent(
    query: str,
    shopping_memory: dict | None = None,
    memory=None,
) -> tuple[str, dict]:
    """Handle shopping follow-up queries that do not require a browser.

    Open-intent follow-ups and new searches are handled in server.py via
    browser_action messages. This function is called only for text-only
    follow-ups (repeat, tell me more, ordinal selection without open intent).
    """
    shopping_memory = shopping_memory or {"last_query": "", "last_results": []}

    if _is_followup_query(query) and shopping_memory.get("last_results"):
        response = _handle_followup_query(query, shopping_memory)
        if memory is not None:
            memory.set_result("shopping", response)
            memory.add_turn("assistant", response, agent="shopping")
        return response, shopping_memory

    return "I couldn't process that shopping request.", shopping_memory
