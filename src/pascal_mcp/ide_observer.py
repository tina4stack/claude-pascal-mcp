"""IDE Observer for RAD Studio / Delphi / Lazarus.

Watches the IDE window via screenshots and reads project source files
from disk. Claude reads compiler errors visually from the screenshot
and uses file access to understand and fix the code.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from pascal_mcp.screenshot import (
    _find_window_by_title,
    _capture_with_printwindow,
    list_windows,
)


# Window class names — primary discriminator. Title-based matching catches
# every Edge tab whose page title happens to mention "RAD Studio", which
# is awkward but harmless until you try to screenshot it.
#
# IMPORTANT: TApplication is intentionally NOT here — it's the main-window
# class of every Delphi-built VCL app (MobaXterm, dozens of others), not
# specific to the IDE itself. Modern RAD Studio uses TAppBuilder.
IDE_WINDOW_CLASSES = {
    "TAppBuilder",     # RAD Studio 11 / 12 / 13
    "TMainIDEMain",    # Some Delphi 7 builds
    "TLazarusIDE",     # Lazarus main IDE window
}

# Title-only fallback patterns (used when no TAppBuilder is found,
# typically because the IDE is on a different desktop or hidden).
IDE_TITLE_PATTERNS = [
    r"Embarcadero RAD Studio \d",  # "Embarcadero RAD Studio 12.x ..."
    r"RAD Studio \d",              # "RAD Studio 13 - ..."
    r"Delphi \d - ",               # "Delphi 7 - ProjectName"
    r"Lazarus IDE v",
]


def _get_window_class(hwnd: int) -> str:
    """Return the Win32 class name of a window (empty string on failure)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(int(hwnd), buf, 256)
    return buf.value


def find_ide_window() -> dict | None:
    """Find a running Delphi / Lazarus IDE window.

    Looks for a window with class TAppBuilder / TMainIDE first — that's
    how Windows itself distinguishes the real IDE from any browser tab
    whose title happens to mention "RAD Studio". Falls back to tightened
    title patterns (e.g. ``RAD Studio 13 - ``) only if no class match is
    found, which covers older Lazarus and edge cases where window
    enumeration misses the main HWND.

    Returns dict with hwnd, title, and parsed project_name, or None.
    """
    windows = list_windows("")

    # Pass 1: match by class (the right discriminator)
    for w in windows:
        try:
            cls = _get_window_class(w["hwnd"])
        except Exception:
            continue
        if cls in IDE_WINDOW_CLASSES:
            return {
                "hwnd": w["hwnd"],
                "title": w["title"],
                "project_name": _parse_project_name(w["title"]),
                "class_name": cls,
            }

    # Pass 2: title-based fallback. Only matches if the title clearly
    # belongs to an IDE (e.g. "RAD Studio 13 - " with a version digit
    # and trailing dash), so Edge tabs showing the RAD Studio docwiki
    # don't false-positive.
    for w in windows:
        title = w["title"]
        for pattern in IDE_TITLE_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return {
                    "hwnd": w["hwnd"],
                    "title": title,
                    "project_name": _parse_project_name(title),
                    "class_name": None,
                }
    return None


def _parse_project_name(title: str) -> str | None:
    """Extract project name from IDE window title.

    RAD Studio: "Embarcadero RAD Studio 12.2 - ProjectName"
    Delphi 7:   "Delphi 7 - ProjectName"
    Lazarus:    "Lazarus IDE v3.0 - ProjectName"
    """
    # Try "- ProjectName" pattern
    match = re.search(r"\s-\s+(.+?)(?:\s*\[|$)", title)
    if match:
        return match.group(1).strip()
    return None


def capture_ide_screenshot(hwnd: int):
    """Capture the IDE window and return a PIL Image, or None on failure.

    RAD Studio 11+ renders its code editor, structure pane, and other
    central panels via Skia on a GPU-composited layer that PrintWindow
    can't reach — it returns a valid bitmap that's almost entirely black.
    We work around it in three stages:

      1. Restore + foreground the window (no-op if it's already there).
         GPU compositing only updates the visible window, so this is the
         precondition for any capture method working at all.
      2. Try PrintWindow first — when it does work (older Delphi /
         Lazarus, non-Skia panels), it gives the cleanest result
         independent of overlapping windows.
      3. Detect the all-black failure mode and fall back to a desktop-DC
         screen crop. The crop picks up whatever's actually under the
         IDE's window rect, which on a foreground window is the IDE.

    Returns None only if both paths fail (e.g. the window vanished or
    has zero area).
    """
    # Lazy imports — these are Windows-only paths the module's top-level
    # imports may not provide on non-Windows hosts.
    from pascal_mcp.screenshot import (
        _bring_window_to_front,
        _capture_via_screen_crop,
        _is_mostly_black,
    )
    import time

    try:
        _bring_window_to_front(hwnd)
    except Exception:
        # If we can't foreground it the screen-crop path is doomed,
        # but PrintWindow might still squeeze something out — push on.
        pass

    # Tiny pause for the compositor to redraw the window now that it's
    # foreground. 200ms is enough for the IDE on a modern box but doesn't
    # add user-visible latency.
    time.sleep(0.2)

    img = _capture_with_printwindow(hwnd)
    if img is not None and not _is_mostly_black(img):
        return img

    # PrintWindow either returned nothing or returned all black — fall back.
    fallback = _capture_via_screen_crop(hwnd)
    if fallback is not None:
        return fallback

    # Last resort: return whatever PrintWindow gave us, even if it's
    # black, so the caller gets *something* and a clearer error message.
    return img


def find_project_files(project_dir: str) -> dict:
    """Scan a Delphi/Lazarus project directory for source files.

    Returns a dict with categorized file lists and parsed project info.
    """
    project_path = Path(project_dir)
    if not project_path.is_dir():
        return {"error": f"Directory not found: {project_dir}"}

    result = {
        "project_dir": str(project_path),
        "dpr_files": [],
        "dproj_files": [],
        "pas_files": [],
        "dfm_files": [],
        "fmx_files": [],
        "lfm_files": [],
        "lpr_files": [],
        "lpi_files": [],
        "units_from_dproj": [],
        "search_paths": [],
        "build_config": None,
    }

    for f in project_path.rglob("*"):
        if f.is_file():
            ext = f.suffix.lower()
            rel = str(f.relative_to(project_path))
            if ext == ".dpr":
                result["dpr_files"].append(rel)
            elif ext == ".dproj":
                result["dproj_files"].append(rel)
            elif ext == ".pas":
                result["pas_files"].append(rel)
            elif ext == ".dfm":
                result["dfm_files"].append(rel)
            elif ext == ".fmx":
                result["fmx_files"].append(rel)
            elif ext == ".lfm":
                result["lfm_files"].append(rel)
            elif ext == ".lpr":
                result["lpr_files"].append(rel)
            elif ext == ".lpi":
                result["lpi_files"].append(rel)

    # Parse .dproj for unit list and build config
    for dproj_rel in result["dproj_files"]:
        dproj_path = project_path / dproj_rel
        try:
            info = _parse_dproj(str(dproj_path))
            result["units_from_dproj"] = info.get("units", [])
            result["search_paths"] = info.get("search_paths", [])
            result["build_config"] = info.get("config")
            break  # Use the first .dproj found
        except Exception:
            pass

    return result


def _parse_dproj(dproj_path: str) -> dict:
    """Parse a .dproj (MSBuild) file for unit references and config."""
    tree = ET.parse(dproj_path)
    root = tree.getroot()

    # Handle MSBuild namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    units = []
    search_paths = []
    config = None

    # Find DCCReference elements (source unit includes)
    for ref in root.iter(f"{ns}DCCReference"):
        include = ref.get("Include", "")
        if include:
            units.append(include)

    # Find search paths
    for prop in root.iter(f"{ns}DCC_UnitSearchPath"):
        if prop.text:
            search_paths.extend(prop.text.split(";"))

    # Find active config
    for prop in root.iter(f"{ns}Config"):
        condition = prop.get("Condition", "")
        if "'$(Config)'" in condition and "==" not in condition:
            config = prop.text
            break
    if not config:
        for prop in root.iter(f"{ns}Config"):
            if prop.text:
                config = prop.text
                break

    return {
        "units": units,
        "search_paths": [p.strip() for p in search_paths if p.strip()],
        "config": config,
    }


def read_source_context(
    file_path: str,
    line: int,
    context_lines: int = 10,
) -> str:
    """Read source file and return lines around the specified line number.

    Returns formatted output with line numbers, highlighting the target line.
    """
    path = Path(file_path)
    if not path.is_file():
        return f"File not found: {file_path}"

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {file_path}: {e}"

    lines = text.splitlines()
    total = len(lines)

    if line < 1 or line > total:
        return f"Line {line} is out of range (file has {total} lines)"

    start = max(0, line - 1 - context_lines)
    end = min(total, line + context_lines)

    output = [f"--- {path.name} (line {line}) ---"]
    for i in range(start, end):
        line_num = i + 1
        marker = " >> " if line_num == line else "    "
        output.append(f"{marker}{line_num:4d} | {lines[i]}")
    output.append(f"--- end ({total} lines total) ---")

    return "\n".join(output)


def resolve_error_file(
    filename: str,
    project_dir: str,
    search_paths: list[str] | None = None,
) -> str | None:
    """Resolve a filename from a compiler error to an absolute path.

    Searches the project directory and any configured search paths.
    """
    # Try as-is (absolute path)
    if os.path.isfile(filename):
        return filename

    project_path = Path(project_dir)

    # Try relative to project dir
    candidate = project_path / filename
    if candidate.is_file():
        return str(candidate)

    # Try in search paths
    if search_paths:
        for sp in search_paths:
            sp_path = Path(sp) if os.path.isabs(sp) else project_path / sp
            candidate = sp_path / filename
            if candidate.is_file():
                return str(candidate)

    # Recursive search as last resort
    for f in project_path.rglob(filename):
        if f.is_file():
            return str(f)

    return None
