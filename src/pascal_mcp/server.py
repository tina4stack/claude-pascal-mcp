"""Claude Pascal MCP Server.

Exposes Pascal/Delphi compilation and execution tools via the
Model Context Protocol (MCP) for use with Claude.
"""

import base64

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image

from pascal_mcp.compiler import (
    cleanup_compile_result,
    compile_and_launch,
    compile_project,
    compile_source,
    detect_compilers,
    run_source,
)
from pascal_mcp.templates import (
    generate_console_project,
    generate_fpc_project,
    generate_vcl_project,
)
from pascal_mcp.form_parser import (
    format_component_list,
    format_summary,
    format_tree,
    parse_form_file,
)
from pascal_mcp.installer import download_and_install_fpc
from pascal_mcp.screenshot import capture_window, list_windows
from pascal_mcp.adb import (
    capture_device_screen,
    get_device_info,
    install_apk,
    key_event,
    launch_app,
    list_devices,
    list_packages,
    pull_file,
    push_file,
    stop_app,
    swipe,
    tap,
    type_text,
)
from pascal_mcp.win_interact import (
    click_window,
    type_in_window,
    send_key_to_window,
)
from pascal_mcp.ide_observer import (
    capture_ide_screenshot,
    find_ide_window,
    find_project_files,
    read_source_context,
    resolve_error_file,
)

mcp = FastMCP(
    "pascal-dev",
    instructions=(
        "IMPORTANT: Always use these tools for Pascal/Delphi compilation "
        "and execution. NEVER use MSBuild, shell commands, or other build "
        "systems directly — these tools handle all compiler invocation, "
        "project structure, and output capture automatically. "
        "Use get_compiler_info to check available compilers. "
        "Use compile_pascal to compile single-file source code. "
        "Use compile_delphi_project to compile multi-file Delphi projects "
        "(DPR + PAS + DFM) — this is the correct way to build Delphi apps, "
        "it generates proper project structure and invokes the compiler. "
        "Use run_pascal to compile and execute console programs. "
        "Use launch_app for GUI applications that need to stay running. "
        "If no compiler is found, use setup_fpc to install Free Pascal. "
        "Use parse_form to read DFM/FMX/LFM form files. "
        "Use screenshot_app to capture Windows app windows, then "
        "app_click, app_type, and app_key to interact with them. "
        "Use adb_devices to list connected Android devices. Use adb_screenshot "
        "to capture the device screen. Use adb_tap, adb_swipe, adb_type_text, "
        "and adb_key for UI automation. Use adb_install, adb_launch_app, "
        "adb_stop_app for app management. Use adb_push and adb_pull for "
        "file transfer. All ADB tools accept an optional device serial."
    ),
)


@mcp.tool()
async def get_compiler_info() -> str:
    """Detect available Pascal compilers and return their details.

    Checks for Free Pascal (fpc), Delphi 32-bit (dcc32), and Delphi 64-bit (dcc64)
    on the system PATH and in common installation directories.

    Returns a summary of all compilers found with name, version, and path.
    """
    compilers = detect_compilers()

    if not compilers:
        return (
            "No Pascal compilers found on this system.\n\n"
            "Available options:\n"
            "  - Use the setup_fpc tool to download and install Free Pascal\n"
            "  - Install Lazarus IDE (includes FPC): https://www.lazarus-ide.org\n"
            "  - Install RAD Studio: https://www.embarcadero.com/products/rad-studio"
        )

    lines = [f"Found {len(compilers)} Pascal compiler(s):\n"]
    for c in compilers:
        lines.append(f"  [{c.compiler_type}] {c.name}")
        lines.append(f"    Version: {c.version}")
        lines.append(f"    Path:    {c.path}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def compile_pascal(
    source_code: str,
    compiler: str | None = None,
) -> str:
    """Compile Pascal source code and return compiler output.

    Use this to check if code compiles without running it. Returns compiler
    messages including any errors or warnings.

    Args:
        source_code: The complete Pascal source code to compile. Should include
            the program/unit header (e.g., 'program Hello;').
        compiler: Which compiler to use. Can be a type name ('fpc', 'dcc32',
            'dcc64') or a full path to a specific compiler executable (e.g.,
            'C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0\\bin\\dcc64.exe').
            If not specified, auto-selects the best available compiler.
    """
    result = compile_source(source_code, compiler_type=compiler)

    parts = [f"Compiler: {result.compiler_used}"]
    parts.append(f"Success: {result.success}")
    parts.append(f"Exit code: {result.exit_code}")

    if result.stdout.strip():
        parts.append(f"\n--- Compiler Output ---\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"\n--- Compiler Messages ---\n{result.stderr.strip()}")

    # Clean up temp files
    cleanup_compile_result(result)

    return "\n".join(parts)


@mcp.tool()
async def run_pascal(
    source_code: str,
    compiler: str | None = None,
    stdin_input: str = "",
) -> str:
    """Compile and execute Pascal source code, returning the program output.

    Compiles the source code, runs the resulting executable, and returns
    both compilation messages and program output (stdout/stderr).

    Args:
        source_code: The complete Pascal source code to compile and run.
            Should be a program (not a unit) with a begin..end block.
        compiler: Which compiler to use. Can be a type name ('fpc', 'dcc32',
            'dcc64') or a full path to a specific compiler executable (e.g.,
            'C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0\\bin\\dcc64.exe').
            If not specified, auto-selects the best available compiler.
        stdin_input: Optional text input to send to the program's stdin.
            Useful for programs that read from input.
    """
    result = run_source(
        source_code,
        compiler_type=compiler,
        stdin_input=stdin_input,
    )

    parts = [f"Compiler: {result.compiler_used}"]
    parts.append(f"Success: {result.success}")
    parts.append(f"Exit code: {result.exit_code}")

    if result.stdout.strip():
        parts.append(f"\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"\n--- Errors ---\n{result.stderr.strip()}")

    return "\n".join(parts)


@mcp.tool()
async def check_syntax(
    source_code: str,
    compiler: str | None = None,
) -> str:
    """Check Pascal syntax without producing an executable.

    Performs a syntax-only check (no linking). Faster than a full compile
    and useful for quickly validating code structure.

    Args:
        source_code: The Pascal source code to check.
        compiler: Which compiler to use. Can be a type name ('fpc', 'dcc32',
            'dcc64') or a full path to a specific compiler executable.
            If not specified, auto-selects the best available compiler.
    """
    result = compile_source(source_code, compiler_type=compiler, syntax_only=True)

    parts = [f"Compiler: {result.compiler_used}"]

    if result.success:
        parts.append("Syntax check: PASSED")
    else:
        parts.append("Syntax check: FAILED")

    if result.stdout.strip():
        parts.append(f"\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"\n{result.stderr.strip()}")

    # Clean up temp files
    cleanup_compile_result(result)

    return "\n".join(parts)


@mcp.tool()
async def parse_form(
    file_path: str,
    output_format: str = "tree",
) -> str:
    """Parse a Delphi/Lazarus form file and return its component structure.

    Reads .dfm (VCL), .fmx (FireMonkey), or .lfm (Lazarus) form files
    and returns a structured view of all components, their properties,
    positions, sizes, and event handlers.

    Args:
        file_path: Absolute path to the .dfm, .fmx, or .lfm file.
        output_format: How to format the output:
            - 'tree': Indented component tree with key properties (default)
            - 'summary': High-level overview with component counts and events
            - 'flat': Flat list of all components with position/size info
    """
    try:
        root = parse_form_file(file_path)
    except ValueError as e:
        return str(e)

    if root is None:
        return f"Could not parse form file: {file_path}"

    if output_format == "summary":
        return format_summary(root)
    elif output_format == "flat":
        return format_component_list(root)
    else:
        return format_tree(root)


@mcp.tool()
async def screenshot_app(
    window_title: str,
) -> list:
    """Take a screenshot of a running application window.

    Finds a window by its title (or partial title) and captures just
    that window as a PNG image without stealing focus or disrupting
    the user's desktop.
    Use list_app_windows first if you need to find the exact title.

    Args:
        window_title: Full or partial window title to capture (case-insensitive).
            For example: 'Hello World App' or just 'Hello'.
    """
    result = capture_window(window_title)

    if result is None:
        windows = list_windows(window_title)
        if windows:
            titles = "\n".join(f"  - {w['title']}" for w in windows[:10])
            return f"Window not found for '{window_title}'. Similar windows:\n{titles}"
        return (
            f"No window found matching '{window_title}'. "
            "Use the list_app_windows tool to see all open windows."
        )

    b64_data, actual_title, width, height = result
    return [
        Image(data=base64.b64decode(b64_data), format="png"),
        f"Screenshot of '{actual_title}' ({width}x{height})",
    ]


@mcp.tool()
async def list_app_windows(
    filter_text: str = "",
) -> str:
    """List visible application windows on the desktop.

    Use this to find the exact title of a window before taking
    a screenshot with screenshot_app.

    Args:
        filter_text: Optional text to filter window titles (case-insensitive).
            Leave empty to list all visible windows.
    """
    windows = list_windows(filter_text)

    if not windows:
        if filter_text:
            return f"No visible windows matching '{filter_text}'."
        return "No visible windows found."

    lines = [f"Found {len(windows)} window(s):\n"]
    for w in windows:
        lines.append(f"  {w['title']}")

    return "\n".join(lines)


@mcp.tool()
async def launch_app(
    source_code: str,
    compiler: str | None = None,
) -> str:
    """Compile Pascal source and launch the GUI application in background.

    Use this for GUI applications (VCL/FMX) that need to stay running
    so you can see and interact with them. Unlike run_pascal, this does
    not wait for the program to finish — it launches and returns immediately.

    After launching, use the preview system (preview_start with
    "pascal-preview") to see the running application, or use
    screenshot_app to capture a screenshot.

    Args:
        source_code: The complete Pascal source code to compile and launch.
            Should be a GUI program (VCL/FMX) with forms.
        compiler: Which compiler to use. Can be a type name ('fpc', 'dcc32',
            'dcc64') or a full path to a specific compiler executable.
            If not specified, auto-selects the best available compiler.
    """
    result = compile_and_launch(source_code, compiler_type=compiler)

    parts = [f"Success: {result.success}"]
    parts.append(result.message)

    if result.exe_path:
        parts.append(f"Executable: {result.exe_path}")

    if result.success:
        parts.append(
            "\nTo see the app, use preview_start('pascal-preview') or "
            "screenshot_app with the window title."
        )

    return "\n".join(parts)


@mcp.tool()
async def compile_delphi_project(
    project_name: str = "Project1",
    form_caption: str = "My Application",
    components: str = "[]",
    events: str = "[]",
    compiler: str | None = None,
    output_dir: str | None = None,
    project_type: str = "vcl",
    program_body: str = "",
) -> str:
    """Compile a Delphi project using proper templates (DPR + PAS + DFM).

    This is the ONLY correct way to build Delphi applications — do NOT
    use MSBuild, shell commands, or other build systems. This tool
    generates proper project structure and invokes the Delphi compiler
    (dcc32/dcc64) or Free Pascal directly.

    Args:
        project_name: Name for the project (e.g., 'HelloWorld').
        form_caption: Title bar text for the main form (VCL only).
        components: JSON array of components. Each component is an object:
            [{"type": "TButton", "name": "btnHello", "caption": "Say Hello",
              "left": 130, "top": 120, "width": 140, "height": 45,
              "event": "btnHelloClick"}]
            Supported types: TButton, TEdit, TLabel, TMemo.
        events: JSON array of event handlers:
            [{"name": "btnHelloClick", "body": "ShowMessage('Hello!');"}]
        compiler: Which compiler to use ('fpc', 'dcc32', 'dcc64', or full path).
        output_dir: Optional directory for output files. If not specified,
            uses a temp directory.
        project_type: 'vcl' for GUI app, 'console' for console app, 'fpc' for FPC.
        program_body: For console/fpc projects, the main program code.
    """
    import json

    try:
        comp_list = json.loads(components) if components else []
    except json.JSONDecodeError as e:
        return f"Invalid components JSON: {e}"

    try:
        evt_list = json.loads(events) if events else []
    except json.JSONDecodeError as e:
        return f"Invalid events JSON: {e}"

    # Generate project files from templates
    if project_type == "vcl":
        files = generate_vcl_project(
            project_name=project_name,
            form_caption=form_caption,
            components=comp_list,
            events=evt_list,
            compiler_type=compiler,
        )
    elif project_type == "console":
        body = program_body or "    Writeln('Hello, World!');"
        files = generate_console_project(
            project_name=project_name,
            program_body=body,
            compiler_type=compiler,
        )
    elif project_type == "fpc":
        body = program_body or "  Writeln('Hello, World!');"
        files = generate_fpc_project(
            project_name=project_name,
            program_body=body,
        )
    else:
        return f"Unknown project_type: {project_type}. Use 'vcl', 'console', or 'fpc'."

    # Show what was generated
    parts = [f"Generated {len(files)} file(s):"]
    for fname in files:
        parts.append(f"  - {fname}")

    # Compile the project
    result = compile_project(files, compiler_type=compiler, output_dir=output_dir)

    parts.append(f"\nCompiler: {result.compiler_used}")
    parts.append(f"Success: {result.success}")

    if result.stdout.strip():
        parts.append(f"\n--- Compiler Output ---\n{result.stdout.strip()}")
    if result.stderr.strip():
        parts.append(f"\n--- Compiler Messages ---\n{result.stderr.strip()}")

    if result.exe_path:
        parts.append(f"\nExecutable: {result.exe_path}")

    if not output_dir and result.exe_path:
        parts.append("\nNote: Files are in a temp directory. Use output_dir to save permanently.")

    return "\n".join(parts)


@mcp.tool()
async def setup_fpc(
    install_dir: str = r"C:\FPC\3.2.2",
) -> str:
    """Download and install Free Pascal Compiler (FPC).

    Only use this when no Pascal compiler is available on the system.
    Downloads FPC 3.2.2 from the official SourceForge mirror and performs
    a silent installation. May require administrator privileges.

    Args:
        install_dir: Where to install FPC. Defaults to C:\\FPC\\3.2.2.
            Avoid paths with spaces.
    """
    result = await download_and_install_fpc(install_dir)

    parts = [f"Status: {result['status']}"]
    parts.append(result["message"])

    if "version" in result:
        parts.append(f"Version: {result['version']}")
    if "path" in result:
        parts.append(f"Path: {result['path']}")

    return "\n".join(parts)


@mcp.tool()
async def observe_ide(
    project_dir: str | None = None,
) -> list:
    """Observe the Delphi/Lazarus IDE and return a screenshot plus project info.

    Finds a running RAD Studio, Delphi, or Lazarus IDE window, captures
    a screenshot of it, and optionally scans the project directory for
    source files. Claude reads the screenshot to spot compiler errors,
    warnings, or other messages in the IDE's Messages pane.

    Args:
        project_dir: Optional path to the project directory on disk.
            If provided, also returns a list of project source files.
    """
    ide = find_ide_window()
    if ide is None:
        return "No Delphi/Lazarus IDE window found. Is RAD Studio running?"

    img = capture_ide_screenshot(ide["hwnd"])
    if img is None:
        return f"Found IDE window '{ide['title']}' but failed to capture screenshot."

    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    png_data = buffer.getvalue()

    result = [
        Image(data=png_data, format="png"),
        f"IDE: {ide['title']}",
    ]

    if ide["project_name"]:
        result.append(f"Project: {ide['project_name']}")

    if project_dir:
        files = find_project_files(project_dir)
        if "error" in files:
            result.append(f"Project scan: {files['error']}")
        else:
            summary = []
            for key in ["pas_files", "dfm_files", "fmx_files", "dpr_files", "dproj_files"]:
                count = len(files.get(key, []))
                if count:
                    summary.append(f"{count} {key.replace('_files', '').upper()}")
            if summary:
                result.append(f"Project files: {', '.join(summary)}")
            if files.get("units_from_dproj"):
                result.append(f"Units in .dproj: {', '.join(files['units_from_dproj'])}")

    return result


@mcp.tool()
async def read_ide_errors(
    project_dir: str,
    errors: str,
) -> str:
    """Read source code context around compiler error locations.

    After spotting errors in an IDE screenshot, call this tool with the
    parsed error locations to get the source code around each error.

    Args:
        project_dir: Path to the project directory on disk.
        errors: JSON array of error locations. Each entry is an object
            with 'file' and 'line' keys, e.g.:
            [{"file": "Unit1.pas", "line": 42},
             {"file": "MainForm.pas", "line": 15}]
    """
    import json

    try:
        error_list = json.loads(errors) if errors else []
    except json.JSONDecodeError as e:
        return f"Invalid errors JSON: {e}"

    if not error_list:
        return "No errors provided."

    # Get search paths from project
    project_info = find_project_files(project_dir)
    search_paths = project_info.get("search_paths", [])

    parts = []
    for err in error_list:
        filename = err.get("file", "")
        line = err.get("line", 0)

        if not filename:
            parts.append("Skipped entry with no filename.")
            continue

        resolved = resolve_error_file(filename, project_dir, search_paths)
        if resolved is None:
            parts.append(f"Could not find file: {filename}")
            continue

        context = read_source_context(resolved, line)
        parts.append(context)

    return "\n\n".join(parts)


@mcp.tool()
async def list_project_files(
    project_dir: str,
) -> str:
    """List all source files in a Delphi/Lazarus project directory.

    Scans the directory for Pascal source files (.pas, .dpr, .lpr),
    form files (.dfm, .fmx, .lfm), and project files (.dproj, .lpi).
    Also parses .dproj files for unit references, search paths, and
    build configuration.

    Args:
        project_dir: Path to the project directory on disk.
    """
    files = find_project_files(project_dir)

    if "error" in files:
        return files["error"]

    parts = [f"Project directory: {files['project_dir']}\n"]

    categories = [
        ("DPR (Delphi project)", "dpr_files"),
        ("DPROJ (MSBuild project)", "dproj_files"),
        ("LPR (Lazarus project)", "lpr_files"),
        ("LPI (Lazarus project info)", "lpi_files"),
        ("PAS (Pascal units)", "pas_files"),
        ("DFM (VCL forms)", "dfm_files"),
        ("FMX (FireMonkey forms)", "fmx_files"),
        ("LFM (Lazarus forms)", "lfm_files"),
    ]

    for label, key in categories:
        file_list = files.get(key, [])
        if file_list:
            parts.append(f"{label}: {len(file_list)}")
            for f in file_list:
                parts.append(f"  - {f}")
            parts.append("")

    if files.get("units_from_dproj"):
        parts.append(f"Units referenced in .dproj:")
        for u in files["units_from_dproj"]:
            parts.append(f"  - {u}")
        parts.append("")

    if files.get("search_paths"):
        parts.append(f"Search paths:")
        for sp in files["search_paths"]:
            parts.append(f"  - {sp}")
        parts.append("")

    if files.get("build_config"):
        parts.append(f"Active build config: {files['build_config']}")

    total = sum(len(files.get(k, [])) for _, k in categories)
    if total == 0:
        parts.append("No Pascal source files found in this directory.")

    return "\n".join(parts)


# --- Windows App Interaction Tools ---


@mcp.tool()
async def app_click(
    window_title: str,
    x: int,
    y: int,
    button: str = "left",
    double_click: bool = False,
) -> str:
    """Click on a Windows application window at the given coordinates.

    Coordinates use screenshot pixels — take a screenshot_app first to
    identify where to click, then use those pixel coordinates here.

    Uses PostMessage with automatic child window targeting so clicks
    reach the correct control (buttons, edits, etc.).

    Args:
        window_title: Full or partial window title (case-insensitive).
        x: X coordinate in screenshot pixels.
        y: Y coordinate in screenshot pixels.
        button: 'left' (default) or 'right'.
        double_click: If True, send a double-click.
    """
    try:
        return click_window(window_title, x, y, button=button, double=double_click)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def app_type(window_title: str, text: str) -> str:
    """Type text into a Windows application window.

    Sends Unicode characters to the window's currently focused control.
    Click on a text field first with app_click to focus it.

    Args:
        window_title: Full or partial window title (case-insensitive).
        text: The text to type.
    """
    try:
        return type_in_window(window_title, text)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def app_key(window_title: str, key: str) -> str:
    """Send a key or keyboard shortcut to a Windows application window.

    Supports special keys: enter, tab, escape, backspace, delete, space,
    up, down, left, right, home, end, pageup, pagedown, f1-f12.

    Supports modifier combinations: ctrl+a, ctrl+shift+s, alt+f4, etc.

    Args:
        window_title: Full or partial window title (case-insensitive).
        key: Key name or combination (e.g., 'enter', 'ctrl+a', 'f5').
    """
    try:
        return send_key_to_window(window_title, key)
    except RuntimeError as e:
        return str(e)


# --- ADB Tools ---


@mcp.tool()
async def adb_devices() -> str:
    """List all connected Android devices with model, Android version, and screen size.

    Returns a formatted table of connected devices. Use this to find
    device serial numbers for targeting specific devices.
    """
    try:
        devices = list_devices()
    except RuntimeError as e:
        return str(e)

    if not devices:
        return "No ADB devices found."

    lines = [f"Found {len(devices)} device(s):\n"]
    for d in devices:
        lines.append(f"  [{d.serial}] {d.model or 'unknown'}")
        lines.append(f"    State: {d.state}")
        if d.android_version:
            lines.append(f"    Android: {d.android_version}")
        if d.screen_size:
            lines.append(f"    Screen: {d.screen_size}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
async def adb_device_info(device: str | None = None) -> str:
    """Get detailed information about a connected Android device.

    Args:
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        d = get_device_info(device)
    except RuntimeError as e:
        return str(e)

    lines = [
        f"Device: {d.serial}",
        f"Model: {d.model or 'unknown'}",
        f"Android: {d.android_version or 'unknown'}",
        f"Screen: {d.screen_size or 'unknown'}",
    ]
    return "\n".join(lines)


@mcp.tool()
async def adb_screenshot(device: str | None = None) -> list:
    """Capture the Android device screen as a screenshot.

    Returns the screen image for visual inspection. Use this to see
    what's currently displayed on the device.

    Args:
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        png_data, width, height = capture_device_screen(device)
    except RuntimeError as e:
        return str(e)

    return [
        Image(data=png_data, format="png"),
        f"Device screenshot ({width}x{height})",
    ]


@mcp.tool()
async def adb_tap(x: int, y: int, device: str | None = None) -> str:
    """Tap a point on the Android device screen.

    Args:
        x: X coordinate in pixels.
        y: Y coordinate in pixels.
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return tap(x, y, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_swipe(
    x1: int, y1: int, x2: int, y2: int,
    duration_ms: int = 300,
    device: str | None = None,
) -> str:
    """Swipe on the Android device screen from one point to another.

    Args:
        x1: Start X coordinate.
        y1: Start Y coordinate.
        x2: End X coordinate.
        y2: End Y coordinate.
        duration_ms: Swipe duration in milliseconds (default 300).
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return swipe(x1, y1, x2, y2, duration_ms=duration_ms, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_type_text(text: str, device: str | None = None) -> str:
    """Type text on the Android device.

    The text is escaped for the adb shell. Spaces and special characters
    are handled automatically. The device must have a text field focused.

    Args:
        text: The text to type.
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return type_text(text, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_key(key: str, device: str | None = None) -> str:
    """Send a key event to the Android device.

    Accepts short aliases: home, back, enter, menu, power, volume_up,
    volume_down, tab, delete, space, escape, dpad_up, dpad_down,
    dpad_left, dpad_right, dpad_center, app_switch, camera.
    Also accepts full KEYCODE_* names or numeric key codes.

    Args:
        key: Key name, alias, or numeric code.
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return key_event(key, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_install(apk_path: str, device: str | None = None) -> str:
    """Install an APK file on the Android device.

    Replaces the existing installation if present (-r flag).

    Args:
        apk_path: Absolute path to the .apk file on the local machine.
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return install_apk(apk_path, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_list_packages(
    filter_text: str = "",
    device: str | None = None,
) -> str:
    """List installed packages on the Android device.

    Args:
        filter_text: Optional text to filter package names (case-insensitive).
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        packages = list_packages(filter_text=filter_text, device=device)
    except RuntimeError as e:
        return str(e)

    if not packages:
        if filter_text:
            return f"No packages matching '{filter_text}'."
        return "No packages found."

    lines = [f"Found {len(packages)} package(s):\n"]
    for pkg in packages:
        lines.append(f"  {pkg}")
    return "\n".join(lines)


@mcp.tool()
async def adb_launch_app(
    package: str,
    activity: str | None = None,
    device: str | None = None,
) -> str:
    """Launch an app on the Android device.

    If no activity is specified, launches the default launcher activity.

    Args:
        package: Package name (e.g., 'com.example.myapp').
        activity: Optional activity name (e.g., '.MainActivity').
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return launch_app(package, activity=activity, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_stop_app(package: str, device: str | None = None) -> str:
    """Force-stop an app on the Android device.

    Args:
        package: Package name (e.g., 'com.example.myapp').
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return stop_app(package, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_push(
    local_path: str,
    remote_path: str,
    device: str | None = None,
) -> str:
    """Push a file from the local machine to the Android device.

    Args:
        local_path: Path to the file on the local machine.
        remote_path: Destination path on the device (e.g., '/sdcard/file.txt').
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return push_file(local_path, remote_path, device=device)
    except RuntimeError as e:
        return str(e)


@mcp.tool()
async def adb_pull(
    remote_path: str,
    local_path: str,
    device: str | None = None,
) -> str:
    """Pull a file from the Android device to the local machine.

    Args:
        remote_path: Path on the device (e.g., '/sdcard/file.txt').
        local_path: Destination path on the local machine.
        device: Device serial number. If omitted, auto-selects when
            only one device is connected.
    """
    try:
        return pull_file(remote_path, local_path, device=device)
    except RuntimeError as e:
        return str(e)


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
