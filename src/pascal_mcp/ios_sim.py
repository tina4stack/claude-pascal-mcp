"""iOS Simulator control wrappers — parity with the adb_* surface.

Built on top of mac_ssh.ssh_run() because xcrun simctl runs on the Mac and
PAClient doesn't expose arbitrary command execution. The IDE drives simctl
itself via PAServer's RPC, but that's not in paclient.exe's CLI surface, so
we just go over SSH directly.

The Mac side must have:
  - SSH Remote Login enabled (System Settings → Sharing)
  - Our public key installed (`ssh-copy-id <user>@<host>` once)
  - Xcode installed (`xcrun simctl` ships with Xcode)
  - At least one simulator runtime installed via Xcode → Settings → Platforms

Each function takes the SSH connection info plus its operation arguments and
returns the SSHResult from running the underlying simctl invocation. The MCP
tool wrappers in server.py format this for human display.
"""

from __future__ import annotations

from pascal_mcp.mac_ssh import SSHResult, shell_quote, ssh_run


def sim_list(
    host: str, user: str, booted_only: bool = False,
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """List simulators known to xcrun simctl.

    With booted_only=True, only shows simulators currently running. JSON
    output is requested so the caller can parse it without scraping text.
    """
    filter_arg = "booted" if booted_only else ""
    cmd = f"xcrun simctl list devices {filter_arg} --json"
    return ssh_run(host, user, cmd.strip(), key_path=key_path, timeout=timeout)


def sim_boot(
    host: str, user: str, udid: str,
    key_path: str | None = None, timeout: int = 60,
) -> SSHResult:
    """Boot a simulator by UDID. No-op if it's already booted."""
    cmd = f"xcrun simctl boot {shell_quote(udid)} 2>&1 || true"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_shutdown(
    host: str, user: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Shut down a simulator. 'booted' shuts down all currently-booted ones."""
    cmd = f"xcrun simctl shutdown {shell_quote(udid)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_install(
    host: str, user: str, app_path: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 120,
) -> SSHResult:
    """Install a .app bundle on a simulator.

    app_path must be a remote path on the Mac (e.g. one in PAServer's scratch
    dir after a build_dproj for iOSSimARM64 with deploy chain). The default
    'booted' targets all currently-booted simulators.
    """
    cmd = f"xcrun simctl install {shell_quote(udid)} {shell_quote(app_path)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_launch(
    host: str, user: str, bundle_id: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Launch an installed app by bundle identifier."""
    cmd = f"xcrun simctl launch {shell_quote(udid)} {shell_quote(bundle_id)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_terminate(
    host: str, user: str, bundle_id: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Terminate a running app by bundle identifier."""
    cmd = f"xcrun simctl terminate {shell_quote(udid)} {shell_quote(bundle_id)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_uninstall(
    host: str, user: str, bundle_id: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Uninstall an app by bundle identifier."""
    cmd = f"xcrun simctl uninstall {shell_quote(udid)} {shell_quote(bundle_id)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_open_url(
    host: str, user: str, url: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Open a URL in the simulator (deep links, web URLs, etc.)."""
    cmd = f"xcrun simctl openurl {shell_quote(udid)} {shell_quote(url)}"
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)


def sim_screenshot_b64(
    host: str, user: str, udid: str = "booted",
    key_path: str | None = None, timeout: int = 30,
) -> SSHResult:
    """Capture a simulator screenshot and return it as base64 PNG over stdout.

    The simctl screenshot tool needs a destination path. We write to a unique
    /tmp file on the Mac, base64 it onto stdout, and clean up. The redirect
    order silences simctl's own diagnostic chatter ("Note: No display
    specified...") so stdout is pure base64 and the caller can decode it
    cleanly.

    macOS mktemp doesn't substitute X's the way GNU mktemp does, so we use
    $$.$RANDOM for uniqueness instead — that's portable across all Mac /
    Linux shells without -- needing an external uuidgen.
    """
    cmd = (
        'tmp="/tmp/simshot.$$.$RANDOM.png"; '
        f"xcrun simctl io {shell_quote(udid)} screenshot \"$tmp\" >/dev/null 2>&1 && "
        'base64 -i "$tmp" 2>/dev/null && rm -f "$tmp"'
    )
    return ssh_run(host, user, cmd, key_path=key_path, timeout=timeout)
