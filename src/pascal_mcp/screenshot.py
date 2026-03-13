"""Window screenshot capture for running Pascal applications.

Uses the Windows API to find a window by title and capture just
that window using PrintWindow — no DPI scaling issues.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import io
import sys
import time

from PIL import Image


# Enable DPI awareness so we get real pixel coordinates
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _find_window_by_title(title: str) -> int | None:
    """Find a window handle by (partial) title match.

    Args:
        title: Full or partial window title to search for (case-insensitive).

    Returns:
        The window handle (HWND), or None if not found.
    """
    if sys.platform != "win32":
        return None

    results: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_callback(hwnd, lparam):
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            window_title = buf.value
            if title.lower() in window_title.lower():
                if ctypes.windll.user32.IsWindowVisible(hwnd):
                    results.append((hwnd, window_title))
        return True

    ctypes.windll.user32.EnumWindows(enum_callback, 0)

    if not results:
        return None

    # Exact match first, then first partial
    for hwnd, window_title in results:
        if window_title.lower() == title.lower():
            return hwnd
    return results[0][0]


def _get_window_title(hwnd: int) -> str:
    """Get the title of a window by handle."""
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _bring_window_to_front(hwnd: int) -> None:
    """Bring a window to the foreground so it can be captured cleanly."""
    SW_RESTORE = 9
    if ctypes.windll.user32.IsIconic(hwnd):
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)

    ctypes.windll.user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)


def _capture_with_printwindow(hwnd: int) -> Image.Image | None:
    """Capture a window using the Win32 PrintWindow API.

    This captures the window content directly from the window manager,
    avoiding DPI scaling issues with screen coordinates.
    """
    # Get window dimensions
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        return None

    # Create a device context and bitmap
    hwnd_dc = ctypes.windll.user32.GetWindowDC(hwnd)
    if not hwnd_dc:
        return None

    try:
        mem_dc = ctypes.windll.gdi32.CreateCompatibleDC(hwnd_dc)
        if not mem_dc:
            return None

        try:
            bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
            if not bitmap:
                return None

            try:
                ctypes.windll.gdi32.SelectObject(mem_dc, bitmap)

                # PrintWindow with PW_RENDERFULLCONTENT (flag 2) for best results
                PW_RENDERFULLCONTENT = 2
                result = ctypes.windll.user32.PrintWindow(hwnd, mem_dc, PW_RENDERFULLCONTENT)

                if not result:
                    # Fallback: try without the flag
                    result = ctypes.windll.user32.PrintWindow(hwnd, mem_dc, 0)

                if not result:
                    return None

                # Read bitmap data into a PIL Image
                # Set up BITMAPINFOHEADER
                class BITMAPINFOHEADER(ctypes.Structure):
                    _fields_ = [
                        ("biSize", ctypes.c_uint32),
                        ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32),
                        ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16),
                        ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32),
                        ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32),
                        ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32),
                    ]

                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = width
                bmi.biHeight = -height  # Negative = top-down DIB
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bmi.biCompression = 0  # BI_RGB

                # Allocate buffer for pixel data
                buf_size = width * height * 4
                buf = ctypes.create_string_buffer(buf_size)

                ctypes.windll.gdi32.GetDIBits(
                    mem_dc, bitmap, 0, height,
                    buf, ctypes.byref(bmi), 0  # DIB_RGB_COLORS
                )

                # Convert BGRA to RGBA
                img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1)
                # Convert to RGB (drop alpha)
                img = img.convert("RGB")

                # Crop out DWM invisible borders (the black areas)
                try:
                    extended = ctypes.wintypes.RECT()
                    DWMWA_EXTENDED_FRAME_BOUNDS = 9
                    dwmapi = ctypes.windll.dwmapi
                    hr = dwmapi.DwmGetWindowAttribute(
                        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                        ctypes.byref(extended), ctypes.sizeof(extended)
                    )
                    if hr == 0:  # S_OK
                        # Calculate crop offsets relative to window rect
                        # Add extra pixels to trim DWM shadow/border artifacts
                        extra = 4
                        crop_left = (extended.left - rect.left) + extra
                        crop_top = extended.top - rect.top
                        crop_right = width - (rect.right - extended.right) - extra
                        crop_bottom = height - (rect.bottom - extended.bottom) - extra
                        if (crop_left > 0 or crop_top > 0
                                or crop_right < width or crop_bottom < height):
                            img = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                except Exception:
                    pass  # If DWM query fails, return uncropped

                # Handle DPI-unaware windows on high-DPI monitors.
                # PrintWindow renders at the window's internal DPI, but
                # GetWindowRect returns physical pixels, leaving black areas.
                # Detect and crop to actual content size, then fill edge remnants.
                dpi_cropped = False
                try:
                    GetDpiForWindow = ctypes.windll.user32.GetDpiForWindow
                    GetDpiForWindow.restype = ctypes.c_uint
                    window_dpi = GetDpiForWindow(hwnd)
                    if window_dpi:
                        monitor = ctypes.windll.user32.MonitorFromWindow(
                            hwnd, 2)  # MONITOR_DEFAULTTONEAREST
                        if monitor:
                            dpi_x = ctypes.c_uint()
                            dpi_y = ctypes.c_uint()
                            hr2 = ctypes.windll.shcore.GetDpiForMonitor(
                                monitor, 0,  # MDT_EFFECTIVE_DPI
                                ctypes.byref(dpi_x), ctypes.byref(dpi_y))
                            if hr2 == 0 and dpi_x.value > window_dpi:
                                scale = window_dpi / dpi_x.value
                                iw, ih = img.size
                                new_w = int(iw * scale)
                                new_h = int(ih * scale)
                                if new_w < iw or new_h < ih:
                                    img = img.crop((0, 0, new_w, new_h))
                                    dpi_cropped = True
                except Exception:
                    pass

                # Only fill edge dark pixels if we did a DPI crop
                # (to clean up the remaining shadow border).
                if dpi_cropped:
                    iw, ih = img.size
                    bg_color = img.getpixel((iw // 2, ih // 2))
                    if all(c <= 30 for c in bg_color[:3]):
                        bg_color = (240, 240, 240)
                    edge = 6
                    pixels = img.load()
                    dark_limit = 30
                    for y in range(ih):
                        for x in range(iw):
                            if x < edge or x >= iw - edge or y < edge or y >= ih - edge:
                                p = pixels[x, y]
                                if p[0] <= dark_limit and p[1] <= dark_limit and p[2] <= dark_limit:
                                    pixels[x, y] = bg_color

                return img

            finally:
                ctypes.windll.gdi32.DeleteObject(bitmap)
        finally:
            ctypes.windll.gdi32.DeleteDC(mem_dc)
    finally:
        ctypes.windll.user32.ReleaseDC(hwnd, hwnd_dc)


def list_windows(filter_text: str = "") -> list[dict[str, str]]:
    """List visible windows, optionally filtered by title.

    Args:
        filter_text: Optional text to filter window titles (case-insensitive).

    Returns:
        List of dicts with 'hwnd' and 'title' keys.
    """
    if sys.platform != "win32":
        return []

    windows: list[dict[str, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_callback(hwnd, lparam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                window_title = buf.value
                if not filter_text or filter_text.lower() in window_title.lower():
                    windows.append({
                        "hwnd": str(hwnd),
                        "title": window_title,
                    })
        return True

    ctypes.windll.user32.EnumWindows(enum_callback, 0)
    return windows


def capture_window(
    title: str,
    bring_to_front: bool = False,
) -> tuple[str, str, int, int] | None:
    """Capture a screenshot of a specific window by title.

    Uses PrintWindow to capture the window content directly without
    needing to bring it to the foreground — this avoids stealing focus
    and disrupting the user's desktop experience.

    Args:
        title: Full or partial window title to capture (case-insensitive).
        bring_to_front: If True, bring the window to the foreground first.
            Default False to avoid disrupting the user.

    Returns:
        Tuple of (base64_png_data, window_title, width, height),
        or None if the window was not found.
    """
    if sys.platform != "win32":
        return None

    hwnd = _find_window_by_title(title)
    if hwnd is None:
        return None

    actual_title = _get_window_title(hwnd)

    # Only bring to front if explicitly requested (e.g. before a click)
    if bring_to_front:
        _bring_window_to_front(hwnd)

    # Capture using PrintWindow API (works without foreground)
    img = _capture_with_printwindow(hwnd)
    if img is None:
        return None

    width, height = img.size

    # Convert to base64 PNG
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    b64_data = base64.standard_b64encode(buffer.getvalue()).decode("ascii")

    return (b64_data, actual_title, width, height)
