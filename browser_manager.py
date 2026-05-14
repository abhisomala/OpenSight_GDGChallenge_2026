"""Track browser windows and foreground focus for OpenSight."""
import ctypes
import ctypes.wintypes
import time

_close_callbacks: list = []
_last_browser_hwnd: int = 0
_opensight_hwnd: int = 0  # set once by desktop_app on startup


def set_opensight_hwnd(hwnd: int) -> None:
    """Store the OpenSight window handle."""
    global _opensight_hwnd
    _opensight_hwnd = hwnd


def set_browser_hwnd(hwnd: int) -> None:
    """Store the latest browser window handle."""
    global _last_browser_hwnd
    _last_browser_hwnd = hwnd


def register(close_fn) -> None:
    """Register a browser close callback."""
    _close_callbacks.append(close_fn)


def close_all() -> None:
    """Close all registered browser windows."""
    global _close_callbacks
    for fn in _close_callbacks:
        try:
            fn()
        except Exception:
            print("[browser_manager] close error")
    _close_callbacks = []


def _force_foreground(hwnd: int) -> None:
    """Bring a window to the front reliably on Windows."""
    if not hwnd:
        return
    try:
        u32 = ctypes.windll.user32
        fg_thread = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
        our_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        if fg_thread != our_thread:
            u32.AttachThreadInput(fg_thread, our_thread, True)
        u32.ShowWindow(hwnd, 9)       # SW_RESTORE
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        if fg_thread != our_thread:
            u32.AttachThreadInput(fg_thread, our_thread, False)
    except Exception:
        print("[browser_manager] focus error")


def focus_browser() -> None:
    """Bring the last opened browser window to the front."""
    _force_foreground(_last_browser_hwnd)


def focus_opensight() -> None:
    """Bring the OpenSight desktop window to the front."""
    _force_foreground(_opensight_hwnd)


def snapshot_chromium_hwnds() -> set[int]:
    """Return the set of all currently visible Chromium HWNDs.

    Call this BEFORE launching a new browser so _find_chromium_hwnd can
    correctly identify the new window by diffing against this snapshot.
    Previously the snapshot was taken inside _find_chromium_hwnd after
    launch, meaning the new window was already present and never detected.
    """
    u32 = ctypes.windll.user32
    hwnds: set[int] = set()

    def _cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(hwnd, buf, 256)
        if "Chrome_WidgetWin" in buf.value:
            hwnds.add(hwnd)
        return True

    cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    u32.EnumWindows(cb_type(_cb), 0)
    return hwnds


def _find_chromium_hwnd(timeout: float = 8.0, seen_before: set | None = None) -> int:
    """Poll for a Chromium window that appeared after a browser launched.

    Pass seen_before=snapshot_chromium_hwnds() captured BEFORE p.chromium.launch()
    so this function correctly identifies the new window. If seen_before is None
    (legacy call sites), an empty set is used — still works when no Chrome was
    open before launch, fragile when Chrome was already running.

    Returns the HWND of the new visible window, or 0 on timeout.
    """
    u32 = ctypes.windll.user32
    deadline = time.monotonic() + timeout

    if seen_before is None:
        seen_before = set()

    while time.monotonic() < deadline:
        time.sleep(0.4)
        current = snapshot_chromium_hwnds()
        new = current - seen_before
        for hwnd in new:
            if u32.IsWindowVisible(hwnd):
                return hwnd

    return 0