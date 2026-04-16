"""
browser_manager.py
Single source of truth for all open browser windows across agents.
Both shopping and research register their close callbacks here so
opening a new tab always closes the previous one regardless of which
agent owned it.
"""

_close_callbacks: list = []


def register(close_fn) -> None:
    """Register a callable that closes an open browser window."""
    _close_callbacks.append(close_fn)


def close_all() -> None:
    """Close every registered browser window and clear the registry."""
    global _close_callbacks
    for fn in _close_callbacks:
        try:
            fn()
        except Exception as e:
            print(f"[browser_manager] close error: {e}")
    _close_callbacks = []