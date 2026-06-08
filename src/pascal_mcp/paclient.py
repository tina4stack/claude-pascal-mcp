"""PAClient.exe wrapper — Embarcadero's CLI for driving PAServer.

PAClient is the Windows-side companion to PAServer (which runs on Mac /
Linux). The IDE invokes it for every cross-platform Embarcadero build:
deploying files to the remote host, codesigning iOS/macOS bundles,
building/installing IPAs, the whole Android packaging pipeline.

We wrap a slice of its surface (the parts useful when you're driving
builds from outside the IDE) as MCP tools:

  * Phase 1 — diagnostic: paserver_info, paserver_check_connection
  * Phase 2 — file transfer: paserver_get, paserver_put, paserver_remove

Higher-level iOS-bundle operations (codesign, IPA assembly/install) will
land in Phase 3 once the foundation is verified against a real PAServer.

Why use paclient directly instead of going through MSBuild for every
remote op? Two reasons:

  1. MSBuild /t:Deploy is opinionated — it deploys what the dproj's
     <Deployment> section says to deploy. For pre-flight checks, ad-hoc
     file pulls (logs, crash reports), or testing whether the remote host
     is even reachable, you want surgical operations, not a full build
     pipeline.

  2. paclient.exe handles the auth and protocol with PAServer for us.
     We can pass the registry's already-encrypted password via -pk and
     never have to touch Delphi's password obfuscation algorithm.

The module is Windows-only (PAClient is a Windows binary). On other
platforms find_paclient() returns None and the MCP tools refuse with a
clear error.
"""

from __future__ import annotations

import glob
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass


def find_paclient(studio_root: str | None = None) -> str | None:
    """Locate paclient.exe under a RAD Studio install.

    Looks first in the given studio_root's bin/, then sweeps the standard
    Embarcadero Studio install root for the highest version available.
    Returns None on non-Windows or if paclient.exe can't be found.
    """
    if sys.platform != "win32":
        return None

    if studio_root:
        candidate = os.path.join(studio_root, "bin", "paclient.exe")
        if os.path.isfile(candidate):
            return candidate

    # Fall back to highest-version install
    candidates = glob.glob(
        r"C:\Program Files (x86)\Embarcadero\Studio\*\bin\paclient.exe"
    )
    candidates = [c for c in candidates if os.path.isfile(c)]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0]


@dataclass
class PAServerInfo:
    """Parsed output of `paclient -l <profile>`."""
    profile: str
    location: str  # The %APPDATA%\Embarcadero\BDS\<ver>\ dir
    platform: str  # OSX64 / iOSDevice64 / Linux64 / etc.
    host: str
    port: int
    password: str  # encrypted form — pass to -pk verbatim
    sysroot: str

    @property
    def has_address(self) -> bool:
        return bool(self.host) and self.port > 0


def _run_paclient(
    paclient: str, args: list[str], timeout: int = 30
) -> subprocess.CompletedProcess:
    """Run paclient with the given args.

    Note: paclient rejects --utf8encode as the first arg ("Invalid option")
    and the help is ambiguous about correct placement, so we don't pass it.
    The default ASCII output is fine for the regex parser and for tee'ing
    into MCP responses.
    """
    cmd = [paclient, *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )


# Lines look like:
#     Profile: MACBOOK.profile
#    Location: C:\Users\andre\AppData\Roaming\Embarcadero\BDS\37.0\
#    Platform: OSX64
#        Host: 192.168.88.79
#        Port: 64211
#    Password: AB1401D23AF8F3C66832CE6040E1FA2D
#     Sysroot: C:\Users\andre\OneDrive\Documents\Embarcadero\Studio\SDKs\MACBOOK
_PACLIENT_LINE_RE = re.compile(r"^\s*([A-Za-z]+):\s+(.*?)\s*$")


def _profile_exists_in_registry(profile: str, version: str | None) -> bool:
    """Check the HKCU registry for whether this profile is genuinely registered.

    Necessary because `paclient -l <anything>` happily synthesises a default
    profile entry rather than erroring on a typo — so we can't rely on
    paclient's exit code to validate the name. We re-use the registry sniffer
    already implemented in compiler.py for list_remote_profiles.
    """
    # Lazy import to avoid a circular dep at module load: compiler.py may
    # eventually want to import paclient too.
    from pascal_mcp.compiler import (
        _discover_remote_profiles,
        _discover_studio_roots,
        _studio_version_from_root,
    )
    if version is None:
        roots = _discover_studio_roots()
        if not roots:
            return False
        version = _studio_version_from_root(roots[0])
        if version is None:
            return False
    profiles = _discover_remote_profiles(version)
    return any(p.name == profile for p in profiles)


def get_paserver_info(
    paclient: str,
    profile: str,
    timeout: int = 30,
    studio_version: str | None = None,
) -> PAServerInfo | None:
    """Read the local profile info via `paclient -l`.

    Pure local read — does NOT touch the network. We validate the profile
    name against the registry first because paclient itself doesn't error
    on unknown names (it just emits a synthesised "localhost" default).

    Returns None if the profile isn't registered, or if paclient produces
    no parseable output at all.
    """
    if not _profile_exists_in_registry(profile, studio_version):
        return None

    try:
        proc = _run_paclient(paclient, ["-l", profile], timeout=timeout)
    except subprocess.TimeoutExpired:
        return None

    if proc.returncode != 0 and not proc.stdout:
        return None

    fields: dict[str, str] = {}
    for line in (proc.stdout or "").splitlines():
        m = _PACLIENT_LINE_RE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if key in ("Profile", "Location", "Platform", "Host", "Port", "Password", "Sysroot"):
            fields[key] = val

    if "Host" not in fields:
        return None

    try:
        port = int(fields.get("Port") or 0)
    except ValueError:
        port = 0

    return PAServerInfo(
        profile=fields.get("Profile", profile),
        location=fields.get("Location", ""),
        platform=fields.get("Platform", ""),
        host=fields.get("Host", ""),
        port=port,
        password=fields.get("Password", ""),
        sysroot=fields.get("Sysroot", ""),
    )


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """Plain TCP probe to (host, port). Cheap and answers the 90% question.

    Returns (ok, reason). If the port is closed or unreachable we say so;
    if it's open we report it as reachable (doesn't validate that PAServer
    is actually speaking the right protocol — that's what a real paclient
    connection check is for, see check_paserver_connection).
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP {host}:{port} accepted connection"
    except (TimeoutError, socket.timeout):
        return False, f"TCP {host}:{port} timed out after {timeout}s"
    except ConnectionRefusedError:
        return False, f"TCP {host}:{port} refused — PAServer not running on the host?"
    except OSError as e:
        return False, f"TCP {host}:{port} unreachable: {e}"


@dataclass
class ConnectionCheckResult:
    """Combined outcome of a PAServer reachability check."""
    profile: str
    host: str
    port: int
    profile_ok: bool  # paclient -l found the profile
    tcp_ok: bool      # TCP socket reached the host:port
    notes: list[str]


def check_paserver_connection(
    paclient: str,
    profile: str,
    timeout: float = 3.0,
) -> ConnectionCheckResult:
    """Two-stage reachability check for a PAServer Connection Profile.

    1. paclient -l <profile> — confirms the profile exists locally and
       gives us host/port to probe.
    2. TCP connect to that host:port — confirms PAServer is listening.

    We don't push a full protocol handshake (would need to either invoke
    paclient with a real operation, or speak PAServer's wire protocol
    ourselves). For a pre-flight check the two stages above answer 90%
    of "why isn't this working" questions.
    """
    notes: list[str] = []

    info = get_paserver_info(paclient, profile)
    if info is None:
        notes.append(
            f"paclient -l {profile} did not return a recognised profile — "
            "is the name spelled correctly? Check list_remote_profiles."
        )
        return ConnectionCheckResult(
            profile=profile, host="", port=0,
            profile_ok=False, tcp_ok=False, notes=notes,
        )

    notes.append(
        f"Profile found: Platform={info.platform}, "
        f"Sysroot={info.sysroot}"
    )

    if not info.has_address:
        notes.append("Profile has no host/port — TCP probe skipped.")
        return ConnectionCheckResult(
            profile=profile, host=info.host, port=info.port,
            profile_ok=True, tcp_ok=False, notes=notes,
        )

    tcp_ok, reason = tcp_reachable(info.host, info.port, timeout=timeout)
    notes.append(reason)

    return ConnectionCheckResult(
        profile=profile, host=info.host, port=info.port,
        profile_ok=True, tcp_ok=tcp_ok, notes=notes,
    )


# ---------------------------------------------------------------------------
# Phase 2 — file transfer
# ---------------------------------------------------------------------------

def _paclient_conn_args(info: PAServerInfo) -> list[str]:
    """Build the standard -h/-p/-pk auth args from a PAServerInfo."""
    return [
        f"--host={info.host}",
        f"--port={info.port}",
        # Encrypted password from registry/profile; -pk takes it verbatim,
        # no decryption needed on our side.
        f"--passkey={info.password}",
    ]


def paserver_scratch_dir(
    profile: str,
    remote_user: str,
    windows_user: str | None = None,
) -> str:
    """Compose PAServer's conventional per-profile scratch directory path.

    PAServer stages everything under:
        /Users/<remote_user>/PAServer/scratch-dir/<windows_user>-<PROFILE>/

    The remote_user is the Unix account that's running paserver on the
    Mac/Linux host. The windows_user is your local Windows username,
    which paclient derives from %USERNAME% if not passed.

    This dir is the only path writeable in restricted mode (the default),
    and it's where the IDE deploys to as well — so use it for build
    staging, ad-hoc file pushes, and pulling .app / .ipa bundles back
    after a remote build.
    """
    if windows_user is None:
        windows_user = os.environ.get("USERNAME") or "user"
    return f"/Users/{remote_user}/PAServer/scratch-dir/{windows_user}-{profile}"


@dataclass
class TransferResult:
    """Outcome of a file transfer / removal call to paclient."""
    success: bool
    profile: str
    operation: str  # "get" | "put" | "remove"
    output: str     # stdout from paclient
    errors: str     # stderr from paclient


def paserver_get(
    paclient: str,
    profile: str,
    remote_path: str,
    local_dir: str,
    timeout: int = 300,
) -> TransferResult:
    """Pull a file/dir from the remote PAServer host into local_dir.

    Wraps `paclient -g <remote>,<local_dir>`. The remote_path can use
    PAClient's wildcard syntax (e.g. ``logs/*.txt``). The local_dir is
    where the file lands on this Windows box.
    """
    info = get_paserver_info(paclient, profile)
    if info is None:
        return TransferResult(False, profile, "get", "",
                              f"Profile {profile!r} not found")

    os.makedirs(local_dir, exist_ok=True)
    args = [
        *_paclient_conn_args(info),
        f"--get={remote_path},{local_dir}",
        profile,
    ]
    try:
        proc = _run_paclient(paclient, args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return TransferResult(False, profile, "get", "",
                              f"paclient -g timed out after {timeout}s")
    return TransferResult(
        success=proc.returncode == 0,
        profile=profile, operation="get",
        output=proc.stdout or "", errors=proc.stderr or "",
    )


def paserver_put(
    paclient: str,
    profile: str,
    local_path: str,
    remote_dir: str,
    timeout: int = 300,
) -> TransferResult:
    """Push a file/dir from this box to the remote PAServer host.

    Wraps `paclient -u <local>,<remote_dir>`. The local_path can use
    wildcard syntax (e.g. ``build\\*.so``).

    PAServer security note: by default PAServer runs in restricted mode
    and rejects writes outside its per-profile scratch sandbox at
    /Users/<unix-user>/PAServer/scratch-dir/<windows-user>-<PROFILE>/.
    Attempting to write to /tmp or /Users/something-else returns:
        Error: E0006 Copying file(s) to directory outside ... is not
        allowed; PAServer is running in restricted mode

    Either target the scratch dir (paserver_scratch_dir() helps construct
    the path) or have the user start PAServer with -restricted=false on
    the Mac side. The scratch dir is the right answer for build staging
    and ad-hoc file transfer — it's what the IDE uses.
    """
    info = get_paserver_info(paclient, profile)
    if info is None:
        return TransferResult(False, profile, "put", "",
                              f"Profile {profile!r} not found")

    if not (os.path.exists(local_path) or "*" in local_path):
        return TransferResult(False, profile, "put", "",
                              f"local_path does not exist: {local_path}")

    args = [
        *_paclient_conn_args(info),
        f"--put={local_path},{remote_dir}",
        profile,
    ]
    try:
        proc = _run_paclient(paclient, args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return TransferResult(False, profile, "put", "",
                              f"paclient -u timed out after {timeout}s")
    return TransferResult(
        success=proc.returncode == 0,
        profile=profile, operation="put",
        output=proc.stdout or "", errors=proc.stderr or "",
    )


def paserver_remove(
    paclient: str,
    profile: str,
    remote_path: str,
    timeout: int = 60,
) -> TransferResult:
    """Remove a file/dir on the remote PAServer host (paclient -R).

    Note: capital-R removes from the *remote*. Lowercase -r would remove
    from the local cache; we don't expose that — the caller can just
    delete the local file directly with normal filesystem APIs.
    """
    info = get_paserver_info(paclient, profile)
    if info is None:
        return TransferResult(False, profile, "remove", "",
                              f"Profile {profile!r} not found")

    args = [
        *_paclient_conn_args(info),
        f"--Remove={remote_path}",
        profile,
    ]
    try:
        proc = _run_paclient(paclient, args, timeout=timeout)
    except subprocess.TimeoutExpired:
        return TransferResult(False, profile, "remove", "",
                              f"paclient -R timed out after {timeout}s")
    return TransferResult(
        success=proc.returncode == 0,
        profile=profile, operation="remove",
        output=proc.stdout or "", errors=proc.stderr or "",
    )
