"""
Window utility module for Forza Horizon 5 detection.
Provides functions to locate the FH5 window and get dynamic regions for image detection.
"""

import pygetwindow as gw
import pyautogui
import os
import sys




def resource_path(relative_path: str) -> str:
    """Return an absolute path to a resource, handling PyInstaller bundling.

    The assets directory and other data files are stored alongside the
    executable when packaged. During development ``__file__`` is used instead.
    """
    base = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, relative_path)


def get_fh5_window():
    """
    Retrieves the Forza Horizon 5 window object.
    
    Returns:
        pygetwindow.Window: The FH5 window object, or None if not found.
    """
    try:
        windows = gw.getWindowsWithTitle("Forza Horizon 5")
        if windows:
            return windows[0]
        return None
    except Exception as e:
        print(f"⚠️  Error retrieving FH5 window: {e}")
        return None


def get_window_region(window):
    """
    Converts a pygetwindow.Window object to a PyAutoGUI region tuple in physical
    display pixels.

    pygetwindow reports coordinates in **logical** units, which are affected by
    Windows DPI scaling.  Screenshots taken by PyAutoGUI are in physical
    pixels, so we need to scale the window dimensions accordingly or the
    regions will be wrong (as observed when the reported window width was half
    of the true pixel width).

    Args:
        window: A pygetwindow.Window object.

    Returns:
        tuple: (left, top, width, height) suitable for pyautogui.locateOnScreen(),
               or None on error.
    """
    if window is None:
        return None

    try:
        # raw logical values
        left, top, w, h = window.left, window.top, window.width, window.height

        # compute scaling factors between logical system metrics and physical
        import ctypes
        import pyautogui

        logical_w = ctypes.windll.user32.GetSystemMetrics(0)
        logical_h = ctypes.windll.user32.GetSystemMetrics(1)
        phys_w, phys_h = pyautogui.size()

        scale_x = phys_w / logical_w if logical_w else 1.0
        scale_y = phys_h / logical_h if logical_h else 1.0

        scaled = (
            int(left * scale_x),
            int(top * scale_y),
            int(w * scale_x),
            int(h * scale_y),
        )

        return scaled
    except Exception as e:
        print(f"⚠️  Error converting window to region: {e}")
        return None


def is_window_fullscreen_like(window):
    """
    Checks if a window is fullscreen or borderless fullscreen based on size.
    
    Args:
        window: A pygetwindow.Window object.
        
    Returns:
        bool: True if the window is approximately fullscreen size.
    """
    if window is None:
        return False
    
    try:
        screen_w, screen_h = pyautogui.size()
        # Allow small tolerance for window decorations
        width_match = abs(window.width - screen_w) < 10
        height_match = abs(window.height - screen_h) < 10
        return width_match and height_match
    except Exception as e:
        print(f"⚠️  Error checking fullscreen status: {e}")
        return False


def get_fh5_region_safe(fallback_region=None):
    """
    Safely retrieves the FH5 window region with graceful fallback.
    Logs warnings to console if window not found but doesn't crash.
    
    Args:
        fallback_region: Default region to use if FH5 window not found.
                        If None, returns None (caller must handle).
    
    Returns:
        tuple: (left, top, width, height) or fallback_region or None
    """
    window = get_fh5_window()
    
    if window is None:
        print("WARNING: Forza Horizon 5 window not found. Using fallback region.")
        if fallback_region:
            fullscreen = False
        return fallback_region
    
    # Log fullscreen status for debugging
    fullscreen = is_window_fullscreen_like(window)
    mode = "fullscreen-like" if fullscreen else "windowed"
    print(f"FH5 window detected ({mode}): {window.left}, {window.top}, {window.width}x{window.height}")
    
    region = get_window_region(window)
    return region if region else fallback_region


def bottom_left_quarter(region):
    """
    Return a subregion corresponding to the bottom-left quarter of the given region.

    Args:
        region (tuple): (left, top, width, height)

    Returns:
        tuple: cropped region (left, new_top, new_width, new_height)
    """
    if not region:
        return None
    try:
        left, top, width, height = region
        new_width = width // 2
        new_height = height // 2
        # bottom-left: top moves down by half the height
        new_top = top + height - new_height
        return (left, new_top, new_width, new_height)
    except Exception as e:
        print(f"⚠️  Error cropping region to bottom-left quarter: {e}")
        return region


def _get_foreground_window_title():
    """Return the current foreground window title (Unicode)."""
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or ""
    except Exception:
        return ""


def is_fh5_focused():
    """Return True if the foreground window title looks like Forza Horizon.

    This is a lightweight, title-based heuristic. It intentionally uses a
    substring (lowercased) match for robustness against minor title
    variations. This is not foolproof but meets the baseline safety
    requirement.
    """
    try:
        title = _get_foreground_window_title().lower()
        if not title:
            return False
        # be permissive: match 'forza' and optionally 'horizon'
        return "forza" in title
    except Exception:
        return False


def wait_for_fh5_focus(stop_flag=None, check_interval=0.15):
    """Block until FH5 is the foreground window or stop requested.

    Args:
        stop_flag: optional dict with boolean key 'stop' to break waiting.
        check_interval: sleep time between checks (seconds).

    Returns:
        True if focus acquired, False if stop requested first.
    """
    import time

    while True:
        if is_fh5_focused():
            return True
        if stop_flag and stop_flag.get("stop"):
            return False
        time.sleep(check_interval)
