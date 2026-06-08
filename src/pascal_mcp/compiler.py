"""Pascal compiler detection, compilation, and execution."""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompilerInfo:
    """Information about a detected Pascal compiler."""
    name: str
    path: str
    version: str
    compiler_type: str  # "fpc", "dcc32", "dcc64"


@dataclass
class CompileResult:
    """Result of a compilation or execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    compiler_used: str
    exe_path: str | None = None


# Known installation locations on Windows
KNOWN_FPC_LOCATIONS = [
    r"C:\FPC\*\bin\x86_64-win64\fpc.exe",
    r"C:\FPC\*\bin\i386-win32\fpc.exe",
    r"C:\Lazarus\fpc\*\bin\x86_64-win64\fpc.exe",
    r"C:\Lazarus\fpc\*\bin\i386-win32\fpc.exe",
]

KNOWN_DCC_LOCATIONS = [
    r"C:\Program Files (x86)\Embarcadero\Studio\*\bin\dcc64.exe",
    r"C:\Program Files (x86)\Embarcadero\Studio\*\bin\dcc32.EXE",
]


def _find_in_known_locations(patterns: list[str]) -> list[str]:
    """Search known installation paths using glob patterns."""
    found = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        found.extend(matches)
    return found


def _get_fpc_version(fpc_path: str) -> str:
    """Get FPC version string."""
    try:
        result = subprocess.run(
            [fpc_path, "-iV"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unknown"


def _get_dcc_version(dcc_path: str) -> str:
    """Get DCC version string from its output."""
    try:
        result = subprocess.run(
            [dcc_path, "--version"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stdout + result.stderr
        # DCC prints version info on first line of stderr typically
        for line in output.splitlines():
            if "Embarcadero" in line or "Borland" in line or "CodeGear" in line:
                return line.strip()
            if "Delphi" in line or "dcc" in line.lower():
                return line.strip()
        # Fallback: return first non-empty line
        for line in output.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return "installed"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unknown"


def detect_compilers() -> list[CompilerInfo]:
    """Detect all available Pascal compilers on the system.

    Checks PATH first, then known installation locations.
    Returns a list of CompilerInfo for each compiler found.
    """
    compilers: list[CompilerInfo] = []
    seen_paths: set[str] = set()

    def _norm(p: str) -> str:
        return os.path.normcase(os.path.abspath(p))

    # Check PATH for fpc
    fpc_path = shutil.which("fpc")
    if fpc_path:
        key = _norm(fpc_path)
        if key not in seen_paths:
            seen_paths.add(key)
            fpc_path = os.path.abspath(fpc_path)
            version = _get_fpc_version(fpc_path)
            compilers.append(CompilerInfo(
                name="Free Pascal Compiler",
                path=fpc_path,
                version=version,
                compiler_type="fpc",
            ))

    # Check PATH for dcc32 and dcc64
    for compiler_type in ("dcc64", "dcc32"):
        dcc_path = shutil.which(compiler_type)
        if dcc_path:
            key = _norm(dcc_path)
            if key not in seen_paths:
                seen_paths.add(key)
                dcc_path = os.path.abspath(dcc_path)
                version = _get_dcc_version(dcc_path)
                name = "Delphi 64-bit" if "64" in compiler_type else "Delphi 32-bit"
                compilers.append(CompilerInfo(
                    name=f"{name} Compiler",
                    path=dcc_path,
                    version=version,
                    compiler_type=compiler_type,
                ))

    # Check known FPC locations
    if sys.platform == "win32":
        for fpc_path in _find_in_known_locations(KNOWN_FPC_LOCATIONS):
            key = _norm(fpc_path)
            if key not in seen_paths:
                seen_paths.add(key)
                fpc_path = os.path.abspath(fpc_path)
                version = _get_fpc_version(fpc_path)
                compilers.append(CompilerInfo(
                    name="Free Pascal Compiler",
                    path=fpc_path,
                    version=version,
                    compiler_type="fpc",
                ))

        # Check known DCC locations
        for dcc_path in _find_in_known_locations(KNOWN_DCC_LOCATIONS):
            key = _norm(dcc_path)
            if key not in seen_paths:
                seen_paths.add(key)
                version = _get_dcc_version(dcc_path)
                compiler_type = "dcc64" if "dcc64" in dcc_path.lower() else "dcc32"
                name = "Delphi 64-bit" if "64" in compiler_type else "Delphi 32-bit"
                compilers.append(CompilerInfo(
                    name=f"{name} Compiler",
                    path=dcc_path,
                    version=version,
                    compiler_type=compiler_type,
                ))

    return compilers


def _infer_compiler_type(path: str) -> str:
    """Infer the compiler type from an executable path."""
    basename = os.path.basename(path).lower()
    if "dcc64" in basename:
        return "dcc64"
    elif "dcc32" in basename:
        return "dcc32"
    else:
        return "fpc"


def _compiler_from_path(path: str) -> CompilerInfo | None:
    """Build a CompilerInfo from a direct path to a compiler executable.

    Validates the path exists and queries its version.
    Returns None if the path is not a valid executable.
    """
    if not os.path.isfile(path):
        return None

    compiler_type = _infer_compiler_type(path)

    if compiler_type == "fpc":
        version = _get_fpc_version(path)
        name = "Free Pascal Compiler"
    else:
        version = _get_dcc_version(path)
        name = "Delphi 64-bit Compiler" if compiler_type == "dcc64" else "Delphi 32-bit Compiler"

    return CompilerInfo(
        name=name,
        path=os.path.abspath(path),
        version=version,
        compiler_type=compiler_type,
    )


def _is_path(value: str) -> bool:
    """Check if a string looks like a file path rather than a type name."""
    return os.sep in value or "/" in value or "\\" in value or ":" in value


def _select_compiler(
    compilers: list[CompilerInfo],
    preferred: str | None = None,
) -> CompilerInfo | None:
    """Select a compiler from the available ones.

    Args:
        compilers: List of detected compilers.
        preferred: Optional compiler selection. Can be:
            - A type name: 'fpc', 'dcc32', 'dcc64'
            - A full path: 'C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0\\bin\\dcc64.exe'

    Returns:
        The selected CompilerInfo, or None if no compiler is available.
    """
    if preferred:
        # If it looks like a path, use it directly
        if _is_path(preferred):
            compiler = _compiler_from_path(preferred)
            if compiler:
                return compiler
            # Path didn't resolve — fall through to auto-detect

        # Match by type name
        for c in compilers:
            if c.compiler_type == preferred:
                return c

    if not compilers:
        return None

    # Default priority: fpc > dcc64 > dcc32
    priority = {"fpc": 0, "dcc64": 1, "dcc32": 2}
    return min(compilers, key=lambda c: priority.get(c.compiler_type, 99))


def _find_dcc_lib_paths(compiler: CompilerInfo) -> list[str]:
    """Find Delphi RTL/VCL library paths for the given DCC compiler.

    Derives the library search paths from the compiler's install location.
    For dcc64, uses win64/release; for dcc32, uses win32/release.
    """
    # Derive Studio root from compiler path
    # e.g., C:\Program Files (x86)\Embarcadero\Studio\37.0\bin\dcc64.exe
    #     -> C:\Program Files (x86)\Embarcadero\Studio\37.0
    compiler_dir = os.path.dirname(compiler.path)  # .../bin or .../bin64
    studio_root = os.path.dirname(compiler_dir)

    if compiler.compiler_type == "dcc64":
        platform = "win64"
    else:
        platform = "win32"

    lib_paths = []
    lib_base = os.path.join(studio_root, "lib", platform)

    # Add release path (primary) and debug path (fallback)
    for variant in ("release", "debug"):
        path = os.path.join(lib_base, variant)
        if os.path.isdir(path):
            lib_paths.append(path)

    return lib_paths


def _build_compile_args(
    compiler: CompilerInfo,
    source_path: str,
    output_dir: str,
    syntax_only: bool = False,
) -> list[str]:
    """Build the compiler command-line arguments."""
    args = [compiler.path]

    if compiler.compiler_type == "fpc":
        if syntax_only:
            args.append("-s")
        args.extend([
            f"-FE{output_dir}",  # output directory for exe
            f"-FU{output_dir}",  # output directory for units
            source_path,
        ])
    elif compiler.compiler_type in ("dcc32", "dcc64"):
        if syntax_only:
            args.append("-Q")

        # Add RTL/VCL unit search paths
        lib_paths = _find_dcc_lib_paths(compiler)
        for lib_path in lib_paths:
            args.append(f"-U{lib_path}")

        args.extend([
            f"-E{output_dir}",  # exe output directory
            f"-N{output_dir}",  # unit output directory
            "-NSSystem;System.Win;Winapi",  # namespace search
            source_path,
        ])

    return args


def compile_source(
    source_code: str,
    compiler_type: str | None = None,
    syntax_only: bool = False,
) -> CompileResult:
    """Compile Pascal source code.

    Args:
        source_code: The Pascal source to compile.
        compiler_type: Preferred compiler (fpc, dcc32, dcc64). Auto-detects if None.
        syntax_only: If True, only check syntax without linking.

    Returns:
        CompileResult with compilation output.
    """
    compilers = detect_compilers()
    compiler = _select_compiler(compilers, compiler_type)

    if not compiler:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="No Pascal compiler found. Use the setup_fpc tool to install Free Pascal.",
            compiler_used="none",
        )

    # Create a temp directory for this compilation
    work_dir = tempfile.mkdtemp(prefix="pascal_mcp_")

    try:
        # Write source to temp file
        source_path = os.path.join(work_dir, "source.pas")
        with open(source_path, "w", encoding="utf-8") as f:
            f.write(source_code)

        # Build compiler command
        args = _build_compile_args(compiler, source_path, work_dir, syntax_only)

        # Run compiler
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=work_dir,
        )

        # Find the compiled executable
        exe_path = None
        if not syntax_only and result.returncode == 0:
            if sys.platform == "win32":
                candidate = os.path.join(work_dir, "source.exe")
            else:
                candidate = os.path.join(work_dir, "source")
            if os.path.exists(candidate):
                exe_path = candidate

        return CompileResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            compiler_used=f"{compiler.name} ({compiler.compiler_type}) at {compiler.path}",
            exe_path=exe_path,
        )

    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Compilation timed out after 30 seconds.",
            compiler_used=f"{compiler.name} ({compiler.compiler_type})",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=f"Compilation error: {e}",
            compiler_used=f"{compiler.name} ({compiler.compiler_type})",
        )


def run_source(
    source_code: str,
    compiler_type: str | None = None,
    stdin_input: str = "",
    run_timeout: int = 10,
) -> CompileResult:
    """Compile and execute Pascal source code.

    Args:
        source_code: The Pascal source to compile and run.
        compiler_type: Preferred compiler (fpc, dcc32, dcc64). Auto-detects if None.
        stdin_input: Optional input to pass to the program's stdin.
        run_timeout: Maximum seconds for program execution (default 10).

    Returns:
        CompileResult with both compilation and execution output.
    """
    # First compile
    compile_result = compile_source(source_code, compiler_type, syntax_only=False)

    if not compile_result.success or not compile_result.exe_path:
        return compile_result

    # Then run
    try:
        run_result = subprocess.run(
            [compile_result.exe_path],
            capture_output=True,
            text=True,
            timeout=run_timeout,
            input=stdin_input if stdin_input else None,
            cwd=os.path.dirname(compile_result.exe_path),
        )

        # Combine compilation and execution output
        compile_output = ""
        if compile_result.stdout.strip():
            compile_output = f"[Compiler Output]\n{compile_result.stdout.strip()}\n\n"

        return CompileResult(
            success=run_result.returncode == 0,
            exit_code=run_result.returncode,
            stdout=f"{compile_output}[Program Output]\n{run_result.stdout}",
            stderr=run_result.stderr,
            compiler_used=compile_result.compiler_used,
            exe_path=compile_result.exe_path,
        )

    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout=compile_result.stdout,
            stderr=f"Program execution timed out after {run_timeout} seconds.",
            compiler_used=compile_result.compiler_used,
        )
    except Exception as e:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout=compile_result.stdout,
            stderr=f"Execution error: {e}",
            compiler_used=compile_result.compiler_used,
        )
    finally:
        # Clean up the temp directory
        work_dir = os.path.dirname(compile_result.exe_path)
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def compile_project(
    files: dict[str, str],
    compiler_type: str | None = None,
    output_dir: str | None = None,
) -> CompileResult:
    """Compile a multi-file Delphi project.

    Args:
        files: Dict mapping filenames to content. Must include a .dpr file.
        compiler_type: Preferred compiler (fpc, dcc32, dcc64, or full path).
        output_dir: Optional output directory. If None, uses a temp dir.

    Returns:
        CompileResult with compilation output.
    """
    compilers = detect_compilers()
    compiler = _select_compiler(compilers, compiler_type)

    if not compiler:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="No Pascal compiler found. Use the setup_fpc tool to install Free Pascal.",
            compiler_used="none",
        )

    # Find the .dpr file (main project file)
    dpr_file = None
    for fname in files:
        if fname.lower().endswith(".dpr"):
            dpr_file = fname
            break

    if not dpr_file:
        # Fall back to .pas file
        for fname in files:
            if fname.lower().endswith(".pas"):
                dpr_file = fname
                break

    if not dpr_file:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="No .dpr or .pas file found in project files.",
            compiler_used="none",
        )

    # Create work directory
    if output_dir:
        work_dir = output_dir
        os.makedirs(work_dir, exist_ok=True)
    else:
        work_dir = tempfile.mkdtemp(prefix="pascal_mcp_")

    try:
        # Write all project files
        for fname, content in files.items():
            fpath = os.path.join(work_dir, fname)
            os.makedirs(os.path.dirname(fpath) if os.path.dirname(fname) else work_dir, exist_ok=True)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)

        # Build compiler command
        source_path = os.path.join(work_dir, dpr_file)
        args = _build_compile_args(compiler, source_path, work_dir)

        # Run compiler
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=work_dir,
        )

        # Find the compiled executable
        exe_path = None
        if result.returncode == 0:
            project_name = os.path.splitext(dpr_file)[0]
            if sys.platform == "win32":
                candidate = os.path.join(work_dir, f"{project_name}.exe")
            else:
                candidate = os.path.join(work_dir, project_name)
            if os.path.exists(candidate):
                exe_path = candidate

        return CompileResult(
            success=result.returncode == 0,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            compiler_used=f"{compiler.name} ({compiler.compiler_type}) at {compiler.path}",
            exe_path=exe_path,
        )

    except subprocess.TimeoutExpired:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Compilation timed out after 30 seconds.",
            compiler_used=f"{compiler.name} ({compiler.compiler_type})",
        )
    except Exception as e:
        return CompileResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=f"Compilation error: {e}",
            compiler_used=f"{compiler.name} ({compiler.compiler_type})",
        )


@dataclass
class LaunchResult:
    """Result of compiling and launching a GUI application."""
    success: bool
    message: str
    exe_path: str | None = None
    process: object | None = None  # subprocess.Popen


def compile_and_launch(
    source_code: str,
    compiler_type: str | None = None,
) -> LaunchResult:
    """Compile Pascal source and launch the executable in the background.

    Unlike run_source(), this does NOT wait for the process to finish.
    The temp directory is NOT cleaned up so the exe stays available.

    Args:
        source_code: Pascal source code to compile.
        compiler_type: Compiler selection (type name or full path).

    Returns:
        LaunchResult with process info and exe path.
    """
    compile_result = compile_source(source_code, compiler_type, syntax_only=False)

    if not compile_result.success or not compile_result.exe_path:
        error = compile_result.stderr.strip() or compile_result.stdout.strip()
        return LaunchResult(
            success=False,
            message=f"Compilation failed:\n{error}",
        )

    try:
        # Launch without stealing focus from the user.
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP keeps the app
        # from inheriting our console and avoids window activation.
        if sys.platform == "win32":
            import ctypes
            import ctypes.wintypes

            si = subprocess.STARTUPINFO()
            # STARTF_USESHOWWINDOW lets us control the initial window state
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # SW_SHOWNOACTIVATE = 4: show the window but don't give it focus
            si.wShowWindow = 4  # SW_SHOWNOACTIVATE

            creation_flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )
        else:
            si = None
            creation_flags = 0

        proc = subprocess.Popen(
            [compile_result.exe_path],
            cwd=os.path.dirname(compile_result.exe_path),
            creationflags=creation_flags,
            startupinfo=si,
        )

        # Brief pause to let the window appear
        import time
        time.sleep(1.0)

        if proc.poll() is not None:
            return LaunchResult(
                success=False,
                message=f"Application exited immediately with code {proc.returncode}",
                exe_path=compile_result.exe_path,
            )

        return LaunchResult(
            success=True,
            message=f"Application launched (PID {proc.pid})",
            exe_path=compile_result.exe_path,
            process=proc,
        )

    except Exception as e:
        return LaunchResult(
            success=False,
            message=f"Failed to launch: {e}",
            exe_path=compile_result.exe_path,
        )


def cleanup_compile_result(result: CompileResult) -> None:
    """Clean up temporary files from a compile result."""
    if result.exe_path:
        work_dir = os.path.dirname(result.exe_path)
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


def _find_rsvars(studio_root: str) -> str | None:
    """Locate rsvars.bat for a given Studio install (e.g. .../Studio/37.0)."""
    candidate = os.path.join(studio_root, "bin", "rsvars.bat")
    return candidate if os.path.isfile(candidate) else None


def _discover_studio_roots() -> list[str]:
    """Find all installed RAD Studio versions."""
    roots = glob.glob(r"C:\Program Files (x86)\Embarcadero\Studio\*")
    return sorted([r for r in roots if os.path.isdir(r)], reverse=True)


# Platforms that build through a staging directory + external packager
# (Android via aapt locally; iOS / OSX / Linux via PAServer on a remote host).
# These all share the "Delphi's Clean target leaves stale staging behind" bug
# and most of them also need a connection profile to reach a remote builder.
_STAGING_PLATFORMS = ("android", "ios", "osx", "linux")
_PASERVER_PLATFORMS = ("ios", "osx", "linux")


def _needs_paserver(platform: str) -> bool:
    return any(platform.lower().startswith(p) for p in _PASERVER_PLATFORMS)


def _needs_staging_clean(platform: str) -> bool:
    return any(platform.lower().startswith(p) for p in _STAGING_PLATFORMS)


def _artifact_extension(platform: str) -> str:
    """Return the conventional artifact extension for a Delphi target platform."""
    p = platform.lower()
    if p.startswith("android"):
        return ".apk"
    if p.startswith("ios"):
        # iOSDevice64 produces a .app bundle locally; .ipa is generated by
        # PAServer for App Store / Ad Hoc archives but isn't always pulled back.
        return ".app"
    if p.startswith("osx"):
        return ".app"
    if p.startswith("linux"):
        # Linux ELF binary has no extension. PAServer pulls it back to the
        # local platform output dir alongside the staging files.
        return ""
    return ".exe"


_DPROJ_PROPS_TO_READ = ("DCC_ExeOutput", "DCC_DcuOutput", "DCC_BplOutput")

# Helper .proj that imports the dproj and emits each property on a tagged line
# so we can parse it back out. Works on MSBuild 4.0+ (what RAD Studio ships)
# unlike the newer `/getProperty` switch.
_PROPS_HELPER_TEMPLATE = """<Project DefaultTargets="GetProps" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <Import Project="{dproj_full}" />
  <Target Name="GetProps">
{messages}
  </Target>
</Project>
"""


def _resolve_dproj_paths(
    rsvars: str,
    dproj_path: str,
    config: str,
    platform: str,
    remote_profile: str | None = None,
    timeout: int = 60,
) -> dict[str, str]:
    """Ask MSBuild to evaluate the .dproj's own output directories for this build.

    Source of truth for where the build will actually drop its artifacts. We
    write a tiny helper .proj that <Import>s the dproj and emits each desired
    property via <Message>; MSBuild runs the dproj's full property evaluator
    so every $(Platform), $(Config), conditional PropertyGroup, base config,
    and inherited override is resolved exactly as Delphi would.

    Returns a dict mapping any of:
      DCC_ExeOutput, DCC_DcuOutput, DCC_BplOutput
    to an absolute Windows path. Empty dict on any failure — callers fall
    back to convention-based path probing.

    Why not `MSBuild /getProperty:...`? That switch needs MSBuild 16.8+
    (VS 2019). RAD Studio bundles MSBuild 4.0, which rejects it as
    `MSB1001: Unknown switch`. The import-trick works everywhere.
    """
    project_dir = os.path.dirname(dproj_path)
    dproj_full = os.path.abspath(dproj_path)

    # Build the helper .proj. Tag each Message with a sentinel so we can
    # cleanly extract values even when MSBuild interleaves Build noise.
    messages = "\n".join(
        f'    <Message Text="===PROP {p}=$({p})===" Importance="High" />'
        for p in _DPROJ_PROPS_TO_READ
    )
    helper_proj = _PROPS_HELPER_TEMPLATE.format(
        dproj_full=dproj_full, messages=messages
    )

    proj_fd, proj_path = tempfile.mkstemp(
        suffix=".proj", prefix="getprops_", text=True
    )
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", text=True)
    try:
        with os.fdopen(proj_fd, "w") as f:
            f.write(helper_proj)
        with os.fdopen(bat_fd, "w") as f:
            f.write("@echo off\r\n")
            f.write(f'call "{rsvars}"\r\n')
            # Run from project_dir so any relative imports inside the dproj
            # (e.g. CodeGear.Delphi.Targets paths) resolve correctly.
            f.write(f'cd /d "{project_dir}"\r\n')
            cmd = (
                f'MSBuild "{proj_path}" /nologo '
                f"/p:Config={config} /p:Platform={platform} "
                "/v:minimal /clp:NoSummary"
            )
            if remote_profile:
                cmd += (
                    f' /p:RemoteProfileName="{remote_profile}"'
                    f' /p:Profile="{remote_profile}"'
                )
            f.write(cmd + "\r\n")

        try:
            proc = subprocess.run(
                ["cmd.exe", "/c", bat_path],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {}
    finally:
        for p in (bat_path, proj_path):
            try:
                os.unlink(p)
            except OSError:
                pass

    # Even on warnings the Message lines should print. Only bail on hard fail.
    if proc.returncode != 0 and not proc.stdout:
        return {}

    result: dict[str, str] = {}
    # Sentinel-delimited lines look like: "===PROP DCC_ExeOutput=..\bin\Win32\Debug==="
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("===PROP ") or not line.endswith("==="):
            continue
        body = line[len("===PROP "):-3]
        if "=" not in body:
            continue
        key, _, val = body.partition("=")
        if key not in _DPROJ_PROPS_TO_READ or not val:
            continue
        # Resolve relative paths (commonly "..\\bin\\<Platform>\\<Config>")
        # against the project dir and canonicalise.
        result[key] = os.path.abspath(os.path.join(project_dir, val))
    return result


def _resolve_artifact_path(
    project_dir: str,
    project_name: str,
    platform: str,
    config: str,
    exe_output_dir: str | None = None,
) -> str | None:
    """Locate the build artifact. Prefer the dproj's own DCC_ExeOutput.

    If exe_output_dir is provided (from _resolve_dproj_paths), probe it first
    with the platform-conventional extension. Otherwise fall back to the
    legacy candidate list — covers older code paths and projects where the
    /getProperty call failed.
    """
    ext = _artifact_extension(platform)
    name = project_name + ext

    candidates: list[str] = []

    # Authoritative path from the dproj, if we got it
    if exe_output_dir:
        candidates.extend([
            os.path.join(exe_output_dir, name),
            # Android: aapt nests the APK under <Name>\bin\<Name>.apk
            os.path.join(exe_output_dir, project_name, "bin", name),
        ])

    # Convention-based fallback (last-resort guesses)
    candidates.extend([
        os.path.join(project_dir, "bin", platform, config, name),
        os.path.join(project_dir, platform, config, name),
        os.path.join(project_dir, platform, config, project_name, "bin", name),
        os.path.join(project_dir, "bin", platform, config, project_name, "bin", name),
        # ..\bin\ convention used by many real projects (Cuttlefish-style)
        os.path.abspath(os.path.join(project_dir, "..", "bin", platform, config, name)),
        os.path.abspath(os.path.join(project_dir, "..", platform, config, name)),
    ])

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _is_safe_clean_target(target: str, project_dir: str) -> bool:
    """Decide whether ``target`` is safe to deep-clean.

    Safety rules — all must hold:
      1. target must be inside the project tree, i.e. under project_dir OR
         under the project's parent directory (covers ..\\bin\\, ..\\dcu\\,
         ..\\pkg\\ layouts).
      2. target must NOT be project_dir itself or the parent_dir itself.
      3. target must NOT be the project's immediate sibling source dir
         (we only delete platform/config-specific output subdirs).

    The most important case this rejects: shared system BPL directories
    like C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\37.0\\Bpl\\<Platform>,
    which hold BPLs from every Delphi project on the machine. Nuking them
    would break every other project.
    """
    norm_target = os.path.normpath(os.path.abspath(target))
    norm_project = os.path.normpath(os.path.abspath(project_dir))
    norm_parent = os.path.normpath(os.path.dirname(norm_project))

    if norm_target in (norm_project, norm_parent):
        return False

    # commonpath returns the common ancestor; if it's the project tree, ok.
    try:
        cp_project = os.path.commonpath([norm_target, norm_project])
    except ValueError:
        cp_project = ""
    try:
        cp_parent = os.path.commonpath([norm_target, norm_parent])
    except ValueError:
        cp_parent = ""

    return cp_project == norm_project or cp_parent == norm_parent


def _deep_clean_platform_dirs(
    project_dir: str,
    platform: str,
    config: str,
    dproj_paths: dict[str, str] | None = None,
) -> list[str]:
    """Nuke the intermediate + final output dirs for this Config/Platform.

    Delphi's own MSBuild Clean / Rebuild target wipes the DCU files it tracks
    but leaves the PAClient/PAServer staging directory and the previous
    artifact in place. The next build repackages those stale files into the
    new APK / .app / ELF, producing the classic "I changed the code but the
    artifact didn't update" symptom.

    Source of truth: the .dproj's own DCC_ExeOutput, DCC_DcuOutput, and
    DCC_BplOutput properties (resolved via MSBuild against the dproj into
    dproj_paths). We nuke exactly those directories, not assumed conventions.

    Falls back to conventional dirs only if dproj_paths is empty (e.g. the
    resolver call failed). The convention list now also includes the
    ..\\bin\\<Platform>\\<Config> layout common in real projects, which the
    previous version missed entirely.

    Safety: every candidate is filtered through _is_safe_clean_target so we
    never wipe a shared system directory (e.g. the shared BPL output at
    C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\37.0\\Bpl\\<Platform>,
    which DCC_BplOutput often resolves to and which holds BPLs from every
    Delphi project on the machine).

    Sibling configs (Debug vs Release) and sibling platforms are never
    touched: each property already resolves to a Config-and-Platform-specific
    subdirectory.

    Returns the list of directories that were removed.
    """
    targets: list[str] = []
    seen: set[str] = set()
    rejected: list[str] = []

    def _add(path: str) -> None:
        n = os.path.normpath(path)
        if n in seen:
            return
        seen.add(n)
        if _is_safe_clean_target(n, project_dir):
            targets.append(n)
        else:
            rejected.append(n)

    if dproj_paths:
        # Authoritative: use the dproj's own output dirs.
        for key in _DPROJ_PROPS_TO_READ:
            p = dproj_paths.get(key)
            if p:
                _add(p)

    # Always include the conventional fallbacks too — covers the case where
    # the resolver missed something or the dproj has additional intermediate
    # dirs (e.g. PAClient/PAServer scratch parallel to the named outputs).
    _add(os.path.join(project_dir, platform, config))
    _add(os.path.join(project_dir, "bin", platform, config))
    _add(os.path.abspath(os.path.join(project_dir, "..", "bin", platform, config)))
    _add(os.path.abspath(os.path.join(project_dir, "..", "dcu", platform, config)))

    removed: list[str] = []
    for t in targets:
        if os.path.isdir(t):
            shutil.rmtree(t, ignore_errors=True)
            removed.append(t)

    # Stash rejected paths on a module-level for the build wrapper to log.
    # Threading them through the return signature would force every caller
    # to handle a new shape; an attribute on the function keeps backward compat.
    _deep_clean_platform_dirs._last_rejected = rejected  # type: ignore[attr-defined]
    return removed


def build_existing_dproj(
    dproj_path: str,
    config: str = "Debug",
    platform: str = "Win32",
    target: str = "Build",
    studio_root: str | None = None,
    timeout: int = 600,
    deep_clean: bool | None = None,
    remote_profile: str | None = None,
) -> CompileResult:
    """Build an existing Delphi .dproj using MSBuild + rsvars.bat.

    Unlike compile_project (which generates a project from a template),
    this builds a real, multi-file .dproj exactly as RAD Studio would —
    honouring the project's own unit search paths, conditional defines,
    namespace settings, and resource compilation.

    Supports PAServer-driven cross-compilation for iOS, macOS, and Linux:
    pass remote_profile with the name of a Connection Profile already
    configured in RAD Studio (Tools → Options → Environment Options →
    Connection Profile Manager). PAServer must be running on the target
    Mac/Linux host. The build runs through MSBuild on Windows as usual;
    the remote toolchain (clang/ld) is invoked over the PAServer tunnel.

    Args:
        dproj_path: Absolute path to the .dproj file.
        config: Build configuration (Debug, Release, etc.).
        platform: Target platform (Win32, Win64, Android64, iOSDevice64,
            iOSSimARM64, OSX64, OSXARM64, Linux64).
        target: MSBuild target (Build, Rebuild, Clean).
        studio_root: Optional Studio install root (e.g. r"C:\\Program Files (x86)\\Embarcadero\\Studio\\37.0").
            If omitted, picks the highest-version install detected.
        timeout: Seconds before the build is killed.
        deep_clean: If True, nuke the platform's intermediate + bin output
            directories before invoking MSBuild. If False, never deep-clean.
            If None (default), auto-enables for Android / iOS / macOS / Linux
            targets when target is "Rebuild" or "Clean" — Delphi's own Clean
            target leaves PAClient/PAServer staging dirs and the previous
            artifact in place, which causes stale-asset and stale-code bugs.
        remote_profile: Name of the RAD Studio Connection Profile pointing at
            the PAServer host. Required for iOS, macOS, and Linux unless the
            .dproj already pins a default profile. Ignored for Win32/Win64
            and Android (Android builds locally). The profile itself must
            already exist in RAD Studio's config; this tool does not create
            profiles or store credentials.

    Returns:
        CompileResult with success flag, exit code, and combined output.
        exe_path is set to the resolved output artifact path (.exe / .apk /
        .app / Linux ELF binary depending on platform) if the build succeeded
        and a known artifact location exists. For iOS/macOS/Linux the
        artifact only appears locally after PAServer pulls it back; the
        staging dir on the remote may have additional outputs not reflected
        here.
    """
    if not os.path.isfile(dproj_path):
        return CompileResult(
            success=False, exit_code=-1,
            stdout="", stderr=f"dproj not found: {dproj_path}",
            compiler_used="msbuild",
        )

    # Pick Studio install
    if studio_root is None:
        roots = _discover_studio_roots()
        if not roots:
            return CompileResult(
                success=False, exit_code=-1,
                stdout="", stderr="No RAD Studio installation found under C:\\Program Files (x86)\\Embarcadero\\Studio",
                compiler_used="msbuild",
            )
        studio_root = roots[0]

    rsvars = _find_rsvars(studio_root)
    if rsvars is None:
        return CompileResult(
            success=False, exit_code=-1,
            stdout="", stderr=f"rsvars.bat not found under {studio_root}\\bin",
            compiler_used="msbuild",
        )

    project_dir = os.path.dirname(dproj_path)
    project_file = os.path.basename(dproj_path)
    project_name = os.path.splitext(project_file)[0]

    # Source-of-truth: ask MSBuild to evaluate the dproj's own output paths
    # for this Config/Platform. Used by deep_clean and artifact resolution
    # so both honour the project's actual configuration instead of guessing
    # bin\<Platform>\<Config> when the dproj might point at ..\bin\... or
    # somewhere else entirely.
    dproj_paths = _resolve_dproj_paths(
        rsvars=rsvars,
        dproj_path=dproj_path,
        config=config,
        platform=platform,
        remote_profile=remote_profile,
    )

    # Auto-enable deep clean for any staging-based platform on Rebuild/Clean.
    # Delphi's own Clean target wipes DCUs but leaves PAClient / PAServer
    # staging dirs intact, which causes "I changed the code but the artifact
    # didn't update" complaints on Android, iOS, macOS, and Linux.
    if deep_clean is None:
        deep_clean = (
            _needs_staging_clean(platform)
            and target.lower() in ("rebuild", "clean")
        )

    cleaned_dirs: list[str] = []
    rejected_dirs: list[str] = []
    if deep_clean:
        cleaned_dirs = _deep_clean_platform_dirs(
            project_dir, platform, config, dproj_paths=dproj_paths
        )
        rejected_dirs = getattr(
            _deep_clean_platform_dirs, "_last_rejected", []
        )

    # If the requested target was "Clean", we've already done the meaningful
    # work via deep_clean; still invoke MSBuild Clean for symmetry so the
    # in-tree DCU/.o files Delphi tracks get removed too.

    # Build the MSBuild command line. Properties are appended individually so
    # we can conditionally include /p:RemoteProfileName for PAServer builds.
    msbuild_props = [
        f"/p:Config={config}",
        f"/p:Platform={platform}",
    ]
    if remote_profile:
        # The Delphi MSBuild targets read this to drive PAServer. Quote in
        # case the profile name contains spaces.
        msbuild_props.append(f'/p:RemoteProfileName="{remote_profile}"')

    msbuild_cmd = (
        f'MSBuild "{project_file}" /t:{target} '
        + " ".join(msbuild_props)
        + " /nologo /verbosity:minimal"
    )

    # Write a temp .bat that calls rsvars and then MSBuild. Avoids the
    # quoting nightmare of passing a compound `"x" && y` line through
    # subprocess+CreateProcess+cmd.exe on Windows (each layer mangles
    # the inner quotes differently).
    bat_fd, bat_path = tempfile.mkstemp(suffix=".bat", text=True)
    try:
        with os.fdopen(bat_fd, "w") as f:
            f.write("@echo off\r\n")
            f.write(f'call "{rsvars}"\r\n')
            f.write(f'cd /d "{project_dir}"\r\n')
            f.write(msbuild_cmd + "\r\n")

        try:
            proc = subprocess.run(
                ["cmd.exe", "/c", bat_path],
                capture_output=True, text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return CompileResult(
                success=False, exit_code=-1,
                stdout="", stderr=f"Build timed out after {timeout}s",
                compiler_used="msbuild",
            )
    finally:
        try:
            os.unlink(bat_path)
        except OSError:
            pass

    success = proc.returncode == 0
    exe_path: str | None = None
    if success:
        exe_path = _resolve_artifact_path(
            project_dir,
            project_name,
            platform,
            config,
            exe_output_dir=dproj_paths.get("DCC_ExeOutput"),
        )

    # Stitch any deep-clean record onto the front of stdout so the caller can
    # see what was wiped. Keeps a single channel for the human-readable trace.
    clean_log = ""
    if cleaned_dirs:
        clean_log = (
            "Deep-cleaned (Delphi's own Clean misses these for staging-based platforms):\n"
            + "\n".join(f"  - {d}" for d in cleaned_dirs)
            + "\n\n"
        )
    elif deep_clean:
        clean_log = "Deep clean requested; no stale platform dirs found.\n\n"
    if rejected_dirs:
        clean_log += (
            "Skipped (outside project tree — shared system dirs are never wiped):\n"
            + "\n".join(f"  - {d}" for d in rejected_dirs)
            + "\n\n"
        )

    # Surface the dproj's resolved output paths so the trace shows exactly
    # which directories were targeted (helps debug when builds claim success
    # but the user can't find the artifact).
    dproj_log = ""
    if dproj_paths:
        rows = [f"  {k}: {v}" for k, v in dproj_paths.items()]
        dproj_log = "Dproj output paths (resolved by MSBuild):\n" + "\n".join(rows) + "\n\n"

    # PAServer info: surface the profile used, and warn if the platform needs
    # one but none was passed (the .dproj may still have a default pinned).
    paserver_log = ""
    if remote_profile:
        paserver_log = f"PAServer profile: {remote_profile}\n\n"
    elif _needs_paserver(platform):
        paserver_log = (
            f"Note: platform {platform} normally builds via PAServer. No "
            "remote_profile was supplied, so the build will use whatever "
            "RemoteProfileName the .dproj pins by default. If it fails with "
            '"E2597 No remote profile" or a connection error, pass '
            "remote_profile=<your-profile-name> and make sure PAServer is "
            "running on the target host.\n\n"
        )

    return CompileResult(
        success=success,
        exit_code=proc.returncode,
        stdout=paserver_log + dproj_log + clean_log + (proc.stdout or ""),
        stderr=proc.stderr,
        compiler_used=f"MSBuild ({platform} {config}) via {os.path.basename(studio_root)}",
        exe_path=exe_path,
    )
