# Claude Pascal MCP Server

An MCP (Model Context Protocol) server that lets Claude compile, run, and interact with Pascal/Delphi desktop applications. Supports Free Pascal (fpc), Delphi 32-bit (dcc32), and Delphi 64-bit (dcc64) compilers.

## Features

- **Compiler Detection** — automatically finds Pascal compilers on your system (PATH + known install locations)
- **Compile** — compile single-file Pascal source or multi-file Delphi projects
- **Run** — compile and execute console programs, capturing output
- **Launch GUI Apps** — compile and launch VCL/FMX applications in background (without stealing focus)
- **Project Templates** — generate proper Delphi project structure (DPR + PAS + DFM) automatically
- **Form Parser** — read and understand DFM/FMX/LFM form files
- **Window Screenshots** — capture running desktop app windows (non-intrusive, no focus stealing)
- **Windows App Interaction** — click, type text, and send keyboard shortcuts to desktop app windows
- **Android Device Interaction** — full ADB support: screenshots, tap, swipe, type, key events, app management, file transfer
- **IDE Observer** — capture RAD Studio/Delphi/Lazarus IDE screenshots and read compiler errors
- **Preview Bridge** — live preview of running Pascal apps through Claude's preview system
- **FPC Installer** — download and install Free Pascal if no compiler is available

## Tools

| Tool | Description |
|------|-------------|
| `get_compiler_info` | Detect available compilers and show versions |
| `compile_pascal` | Compile single-file source code |
| `compile_delphi_project` | Compile proper Delphi project from templates (DPR + PAS + DFM) |
| `run_pascal` | Compile and execute console programs |
| `launch_app` | Compile and launch GUI app in background |
| `check_syntax` | Syntax check only (no linking) |
| `parse_form` | Parse DFM/FMX/LFM form files |
| `screenshot_app` | Capture screenshot of a running app window |
| `list_app_windows` | List visible windows on the desktop |
| `app_click` | Click on a Windows app window at screenshot pixel coordinates |
| `app_type` | Type text into a Windows app window |
| `app_key` | Send key or shortcut (e.g., `ctrl+a`, `enter`) to a Windows app |
| `observe_ide` | Capture IDE screenshot and scan project files |
| `read_ide_errors` | Read source code around compiler error locations |
| `list_project_files` | List source files in a Delphi/Lazarus project |
| `adb_devices` | List connected Android devices with model and version |
| `adb_device_info` | Get detailed info for a specific Android device |
| `adb_screenshot` | Capture Android device screen |
| `adb_tap` | Tap a point on the Android device screen |
| `adb_swipe` | Swipe on the Android device screen |
| `adb_type_text` | Type text on the Android device |
| `adb_key` | Send a key event (home, back, enter, etc.) to Android device |
| `adb_install` | Install an APK on the Android device |
| `adb_list_packages` | List installed packages on the Android device |
| `adb_launch_app` | Launch an app on the Android device |
| `adb_stop_app` | Force-stop an app on the Android device |
| `adb_push` | Push a file to the Android device |
| `adb_pull` | Pull a file from the Android device |
| `setup_fpc` | Download and install Free Pascal (fallback) |

## Preview Bridge

The preview bridge lets Claude see and interact with running Pascal desktop applications through its web-based preview system. It serves live screenshots of desktop app windows as a web page.

### How it works

```
Claude Preview Tools (preview_start, preview_screenshot, preview_click)
        | HTTP
        v
Preview Bridge Server (Python/Starlette)
   /               -> HTML page with live screenshot viewer
   /api/screenshot  -> PNG of target window
   /api/controls    -> enumerate child controls with positions
   /api/click       -> click at coordinates or by control hwnd
   /api/type        -> send keystrokes to target window
   /api/move        -> move window to screen position
   /api/resize      -> resize window
        | Win32 PrintWindow API
        v
Running Pascal Desktop Application
```

### API Endpoints

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | HTML page with auto-refreshing screenshot viewer |
| `/api/screenshot` | GET | PNG screenshot of target window |
| `/api/windows` | GET | List visible windows |
| `/api/target` | POST | Set target window by title |
| `/api/controls` | GET | Enumerate child controls (buttons, inputs, etc.) |
| `/api/click` | POST | Click by coordinates or direct control hwnd |
| `/api/type` | POST | Send text or key combos (e.g., `ctrl+a`, `enter`) |
| `/api/drag` | POST | Drag from one point to another |
| `/api/move` | POST | Move target window |
| `/api/resize` | POST | Resize target window |
| `/api/window-info` | GET | Window position, size, and client area offset |
| `/api/console` | GET | Console output from launched apps |
| `/api/launch` | POST | Launch an executable |

### Click Methods

The click endpoint supports three modes, from most to least reliable:

1. **Direct control click** (`{"hwnd": "12345"}`) — sends `BM_CLICK` directly to a control handle. Works regardless of DPI, monitors, or foreground state. Get hwnds from `/api/controls`.
2. **Client-area coordinates** (`{"x": 200, "y": 142, "client": true}`) — uses Win32 `ClientToScreen` for proper DPI handling.
3. **Window-relative coordinates** (`{"x": 312, "y": 261}`) — raw coordinates in the screenshot image space.

## Windows App Interaction

The `app_click`, `app_type`, and `app_key` tools let Claude interact with running Windows desktop applications.

### Workflow

1. Take a screenshot with `screenshot_app` to see the current UI
2. Identify pixel coordinates of the target element (button, text field, etc.)
3. Use `app_click` with those coordinates to click
4. Use `app_type` to enter text into a focused field
5. Use `app_key` to send keyboard shortcuts (`enter`, `ctrl+a`, `alt+f4`, etc.)

Clicks use PostMessage with automatic child window targeting, so they reach the correct control. Typing and key events use SendInput for full Unicode and modifier support.

## Android Device Interaction (ADB)

Full Android device interaction via ADB. All tools accept an optional `device` serial number — auto-selects when only one device is connected.

### Device Management
- `adb_devices` — list connected devices with model, Android version, screen size
- `adb_device_info` — detailed info for a specific device

### Screenshots and UI Automation
- `adb_screenshot` — capture the device screen
- `adb_tap` / `adb_swipe` — touch interaction at pixel coordinates
- `adb_type_text` — type text (auto-escapes for adb shell)
- `adb_key` — send key events with aliases: `home`, `back`, `enter`, `menu`, `power`, `volume_up`, `volume_down`, `tab`, `delete`, `space`, `escape`, `app_switch`

### App Management
- `adb_install` — install APK files
- `adb_list_packages` — list installed packages (with optional filter)
- `adb_launch_app` — launch an app by package name
- `adb_stop_app` — force-stop an app

### File Transfer
- `adb_push` — push files from PC to device
- `adb_pull` — pull files from device to PC

## Project Templates

The `compile_delphi_project` tool generates proper Delphi project structure automatically. You specify components and events, and it creates the correct DPR, PAS, and DFM files.

Templates automatically handle:
- **Modern Delphi** (RAD Studio): namespaced units (`Vcl.Forms`, `System.SysUtils`)
- **Legacy Delphi** (Delphi 7): non-namespaced units (`Forms`, `SysUtils`)
- Form definitions (DFM) with proper component declarations
- Event handler wiring between DFM and PAS files

### Example

```
compile_delphi_project(
  project_name="HelloWorld",
  form_caption="My App",
  components='[{"type": "TButton", "name": "btnHello", "caption": "Click Me",
                "left": 100, "top": 100, "width": 120, "height": 35,
                "event": "btnHelloClick"}]',
  events='[{"name": "btnHelloClick", "body": "ShowMessage(\'Hello!\');"}]',
  compiler="C:\\Path\\To\\dcc64.exe"
)
```

This generates:
- `HelloWorld.dpr` — project file with proper uses clause
- `uMain.pas` — unit with form class, component declarations, event handlers
- `uMain.dfm` — form definition with component properties

## Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A Pascal compiler (Free Pascal, Delphi, or RAD Studio)

### Option 1 — Run from PyPI (recommended)

Once a release is published to PyPI, no clone is needed:

```bash
uvx --from claude-pascal-mcp pascal-mcp
```

### Option 2 — Run straight from GitHub (no PyPI required)

```bash
uvx --from git+https://github.com/tina4stack/claude-pascal-mcp pascal-mcp
```

Pin to a tag for reproducibility: `git+https://github.com/tina4stack/claude-pascal-mcp@v0.1.0`.

### Option 3 — Local development clone

```bash
git clone https://github.com/tina4stack/claude-pascal-mcp.git
cd claude-pascal-mcp

# Install dependencies
uv sync

# Run the MCP server (stdio mode)
uv run pascal-mcp

# Run the preview bridge (HTTP mode)
uv run pascal-preview
```

### Register with Claude Code

PyPI install:

```bash
claude mcp add --transport stdio pascal-dev -- uvx --from claude-pascal-mcp pascal-mcp
```

Git install:

```bash
claude mcp add --transport stdio pascal-dev -- uvx --from git+https://github.com/tina4stack/claude-pascal-mcp pascal-mcp
```

Local clone:

```bash
claude mcp add --transport stdio pascal-dev -- uv run --directory /path/to/claude-pascal-mcp pascal-mcp
```

Or add to your project's `.mcp.json` — pick the form that matches how you installed:

```json
{
  "mcpServers": {
    "pascal-dev": {
      "command": "uvx",
      "args": ["--from", "claude-pascal-mcp", "pascal-mcp"]
    }
  }
}
```

```json
{
  "mcpServers": {
    "pascal-dev": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/tina4stack/claude-pascal-mcp", "pascal-mcp"]
    }
  }
}
```

```json
{
  "mcpServers": {
    "pascal-dev": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/claude-pascal-mcp", "pascal-mcp"]
    }
  }
}
```

### Register with Claude Desktop

Add to your `claude_desktop_config.json` (pick the form matching your install):

```json
{
  "mcpServers": {
    "pascal-dev": {
      "command": "uvx",
      "args": ["--from", "claude-pascal-mcp", "pascal-mcp"]
    }
  }
}
```

```json
{
  "mcpServers": {
    "pascal-dev": {
      "command": "uv",
      "args": ["run", "--directory", "C:/path/to/claude-pascal-mcp", "pascal-mcp"]
    }
  }
}
```

## Releasing

Maintainer notes — cutting a new release publishes to PyPI automatically.

1. Bump `version` in `pyproject.toml`.
2. Commit and tag: `git tag v0.1.0 && git push origin v0.1.0`.
3. GitHub Actions (`.github/workflows/publish.yml`) builds the sdist + wheel, publishes to PyPI via [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), and attaches the artifacts to a GitHub Release.

**One-time PyPI Trusted Publisher setup** (required before the first release):

- Create the project on [pypi.org](https://pypi.org) (or reserve it via a first manual `uv publish`).
- Under *Project → Publishing → Add a new publisher*, configure GitHub Actions:
  - Owner: `tina4stack`
  - Repository: `claude-pascal-mcp`
  - Workflow: `publish.yml`
  - Environment: `pypi`
- In the GitHub repo, create an environment named `pypi` (Settings → Environments).

No API tokens needed — OIDC handles auth.

### Preview Bridge Setup

Add to `.claude/launch.json` in your project root:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "pascal-preview",
      "runtimeExecutable": "/path/to/claude-pascal-mcp/.venv/Scripts/pythonw.exe",
      "runtimeArgs": ["-m", "pascal_mcp.preview_bridge"],
      "port": 18080,
      "autoPort": true
    }
  ]
}
```

Then in Claude Code, use `preview_start("pascal-preview")` to open the preview panel.

## Supported Compilers

The server automatically detects compilers in this priority order:

1. **Free Pascal (fpc)** — open source, cross-platform
2. **Delphi 64-bit (dcc64)** — RAD Studio command-line compiler
3. **Delphi 32-bit (dcc32)** — RAD Studio / Delphi 7 command-line compiler

You can also specify a full path to any compiler executable:
```
compile_pascal(source, compiler="C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0\\bin\\dcc64.exe")
```

Detection checks the system PATH first, then known installation directories:

- `C:\FPC\*\bin\*\fpc.exe`
- `C:\Lazarus\fpc\*\bin\*\fpc.exe`
- `C:\Program Files (x86)\Embarcadero\Studio\*\bin\dcc*.exe`

## License

MIT
