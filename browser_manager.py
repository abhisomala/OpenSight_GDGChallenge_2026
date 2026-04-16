"""
browser_manager.py
Central registry for all open browser windows.
Tracks the last browser HWND so we can bring it to the foreground,
and provides focus_opensight() so the desktop app can reclaim focus.
"""
import ctypes
import ctypes.wintypes
import time

_close_callbacks: list = []
_last_browser_hwnd: int = 0
_opensight_hwnd: int = 0  # set once by desktop_app on startup


def set_opensight_hwnd(hwnd: int) -> None:
    global _opensight_hwnd
    _opensight_hwnd = hwnd


def set_browser_hwnd(hwnd: int) -> None:
    global _last_browser_hwnd
    _last_browser_hwnd = hwnd


def register(close_fn) -> None:
    _close_callbacks.append(close_fn)


def close_all() -> None:
    global _close_callbacks
    for fn in _close_callbacks:
        try:
            fn()
        except Exception as e:
            print(f"[browser_manager] close error: {e}")
    _close_callbacks = []


def _force_foreground(hwnd: int) -> None:
    """Bring a window to the front reliably on Windows."""
    if not hwnd:
        return
    try:
        u32 = ctypes.windll.user32
        # attach to foreground thread so SetForegroundWindow works
        fg_thread = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
        our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_thread != our_thread:
            u32.AttachThreadInput(fg_thread, our_thread, True)
        u32.ShowWindow(hwnd, 9)       # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        if fg_thread != our_thread:
            u32.AttachThreadInput(fg_thread, our_thread, False)
    except Exception as e:
        print(f"[browser_manager] focus error: {e}")


def focus_browser() -> None:
    """Bring the last opened browser window to the front."""
    _force_foreground(_last_browser_hwnd)


def focus_opensight() -> None:
    """Bring the OpenSight desktop window to the front."""
    _force_foreground(_opensight_hwnd)


def _find_chromium_hwnd(timeout: float = 8.0) -> int:
    """
    Poll for a Chromium window that appeared after the browser launched.
    Returns its HWND or 0 on timeout.
    """
    u32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout
    seen_before: set[int] = set()

    # snapshot windows before launch — we want NEW ones
    def _snapshot():
        hwnds: set[int] = set()
        def _cb(hwnd, _):
            buf = ctypes.create_unicode_buffer(256)
            u32.GetClassNameW(hwnd, buf, 256)
            if "Chrome_WidgetWin" in buf.value:
                hwnds.add(hwnd)
            return True
        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        u32.EnumWindows(cb(_cb), 0)
        return hwnds

    seen_before = _snapshot()

    while time.monotonic() < deadline:
        time.sleep(0.4)
        current = _snapshot()
        new = current - seen_before
        for hwnd in new:
            if u32.IsWindowVisible(hwnd):
                return hwnd

    return 0