"""iOS DeployFile manifest detection and synthesis for build_dproj.

PAServer's iOS Deploy target consumes the .dproj's <Deployment> section to
know which files to ship to the Mac for codesign + .app assembly. The IDE
writes 4 entries per Config × Platform on first deploy:

  1. ProjectiOSEntitlements — codesign reads it
  2. ProjectiOSInfoPList   — Info.plist for the bundle
  3. ProjectiOSLaunchScreen — launch storyboard
  4. ProjectOutput         — the actual binary

A project that was renamed or never IDE-deployed to a given iOS target has
no entries (or only stub entries from the old name). Command-line Deploy
won't synthesize them, so it ships nothing and codesign fails with:

  E0264 …/<Proj>.app: No such file or directory

— the .app bundle was never assembled because nothing was shipped.

This module:
  * detects what's missing for a (config, platform, project_name) tuple
  * synthesizes the 4 entries via a surgical text insert (preserves the
    rest of the dproj exactly, no XML re-serialization)
  * always writes a timestamped .bak backup before mutating

Source files don't need to exist on disk at synthesis time — Build is
expected to produce them before Deploy reads them. Pre-build synthesis
is the supported case (e.g. for projects never IDE-deployed to iOS).
"""

from __future__ import annotations

import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"

# The four DeployFile classes required for an iOS Deploy to succeed.
# Order matters only for readability of the synthesised XML.
_IOS_DEPLOY_SPEC: dict[str, dict] = {
    "ProjectiOSEntitlements": {
        "suffix": ".entitlements",
        # Just <Overwrite>true</Overwrite> under <Platform>.
    },
    "ProjectiOSInfoPList": {
        "suffix": ".info.plist",
        "remote_name": "Info.plist",  # the bundle expects exactly this filename
    },
    "ProjectiOSLaunchScreen": {
        "suffix": ".launchscreen",
        "operation": "64",  # signals "launch screen" to PAServer
    },
    "ProjectOutput": {
        "suffix": "",  # the bare binary name
        "remote_name": "PROJECT_NAME",  # replaced at synthesis time
    },
}


@dataclass
class IOSDeployStatus:
    """Result of checking iOS DeployFile entries in a dproj."""
    config: str
    platform: str
    project_name: str
    present_classes: list[str] = field(default_factory=list)
    missing_classes: list[str] = field(default_factory=list)

    @property
    def ready_to_deploy(self) -> bool:
        return not self.missing_classes

    def summary(self) -> str:
        if self.ready_to_deploy:
            return (
                f"iOS deploy manifest OK for {self.project_name} "
                f"({self.config} / {self.platform}) — all 4 entries present."
            )
        return (
            f"iOS deploy manifest INCOMPLETE for {self.project_name} "
            f"({self.config} / {self.platform}). Missing: "
            f"{', '.join(self.missing_classes)}. "
            "Without these, /t:Deploy will produce an empty .app and "
            "codesign will fail with 'No such file or directory'. Pass "
            "synthesize_ios_manifest=True to build_dproj to add the missing "
            "entries automatically (a timestamped .bak backup of the dproj "
            "is written first)."
        )


def _strip_ns(tag: str) -> str:
    """Drop the {namespace} prefix added by ElementTree."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _matches_target_entry(
    deploy_file: ET.Element,
    config: str,
    platform: str,
    project_name: str,
) -> str | None:
    """If this DeployFile is a valid entry for our target tuple, return its Class.

    Rules for "valid":
      * Configuration attribute matches config
      * Class attribute is one of the 4 we care about
      * LocalName references the requested project_name (not an old/stub name)
        — for ProjectOutput, the base filename equals project_name
        — for the other classes, the base filename equals project_name + suffix
      * Has a <Platform Name="<platform>"> child (Delphi treats entries without
        one as inert stubs — what we see for the cuttlefish.* leftovers in
        renamed projects)

    Returns None if any rule fails.
    """
    config_attr = deploy_file.get("Configuration")
    class_attr = deploy_file.get("Class")
    local_name = deploy_file.get("LocalName") or ""

    if config_attr != config or class_attr not in _IOS_DEPLOY_SPEC:
        return None

    spec = _IOS_DEPLOY_SPEC[class_attr]
    expected_suffix = spec["suffix"]
    base = os.path.basename(local_name)
    if base != project_name + expected_suffix:
        return None

    # Must have a <Platform Name="..."> child that matches our build platform.
    # Stub entries (the inert <DeployFile .../> shorthand left behind by
    # project rename) don't, and Delphi ignores them.
    for child in deploy_file:
        if _strip_ns(child.tag) == "Platform" and child.get("Name") == platform:
            return class_attr
    return None


def detect_ios_deploy_entries(
    dproj_path: str,
    config: str,
    platform: str,
    project_name: str,
) -> IOSDeployStatus:
    """Inspect a .dproj and return which of the 4 iOS deploy classes are present.

    Pure read — never mutates the file. Safe to call on any dproj.
    """
    status = IOSDeployStatus(
        config=config, platform=platform, project_name=project_name
    )
    try:
        tree = ET.parse(dproj_path)
    except (ET.ParseError, OSError):
        # Treat unparseable / unreadable as "nothing present" — synthesis is
        # the caller's choice; we don't fabricate findings.
        status.missing_classes = list(_IOS_DEPLOY_SPEC.keys())
        return status

    root = tree.getroot()
    deployment = None
    for elem in root.iter():
        if _strip_ns(elem.tag) == "Deployment":
            deployment = elem
            break

    seen: set[str] = set()
    if deployment is not None:
        for child in deployment:
            if _strip_ns(child.tag) != "DeployFile":
                continue
            cls = _matches_target_entry(child, config, platform, project_name)
            if cls:
                seen.add(cls)

    status.present_classes = sorted(seen)
    status.missing_classes = sorted(set(_IOS_DEPLOY_SPEC) - seen)
    return status


def _build_deploy_file_xml(
    class_name: str,
    local_name: str,
    config: str,
    platform: str,
    project_name: str,
    indent: str = "                ",
) -> str:
    """Build one <DeployFile> XML block matching the IDE's exact shape.

    The IDE writes blocks with a child <Platform> wrapper containing
    per-platform metadata; PAServer Deploy reads those, so stub entries
    without the <Platform> child are silently ignored. We always emit the
    wrapper.
    """
    spec = _IOS_DEPLOY_SPEC[class_name]
    inner_lines = []
    if "remote_name" in spec:
        remote = project_name if spec["remote_name"] == "PROJECT_NAME" else spec["remote_name"]
        inner_lines.append(f"{indent}        <RemoteName>{remote}</RemoteName>")
    if "operation" in spec:
        inner_lines.append(f"{indent}        <Operation>{spec['operation']}</Operation>")
    inner_lines.append(f"{indent}        <Overwrite>true</Overwrite>")
    inner = "\n".join(inner_lines)

    return (
        f'{indent}<DeployFile LocalName="{local_name}" '
        f'Configuration="{config}" Class="{class_name}">\n'
        f'{indent}    <Platform Name="{platform}">\n'
        f"{inner}\n"
        f"{indent}    </Platform>\n"
        f"{indent}</DeployFile>"
    )


def synthesize_ios_deploy_entries(
    dproj_path: str,
    config: str,
    platform: str,
    project_name: str,
    exe_output_dir_relative: str,
    missing_classes: list[str],
    backup: bool = True,
) -> tuple[bool, str, str | None]:
    """Insert missing iOS DeployFile entries directly before </Deployment>.

    Surgical text insert — never re-serializes the dproj XML. Indentation,
    comments, blank lines, attribute ordering elsewhere are untouched.

    Args:
        dproj_path: Absolute path to the .dproj.
        config: Build configuration (Debug, Release, …).
        platform: Build platform (iOSSimARM64, iOSDevice64, …).
        project_name: Binary name (the .dproj base name without extension).
        exe_output_dir_relative: Path that should precede each LocalName,
            relative to project_dir. For the standard "..\\bin\\$(Platform)\\$(Config)"
            layout this is "..\\bin\\<Platform>\\<Config>". Caller computes
            this from the resolved DCC_ExeOutput.
        missing_classes: Which of the 4 classes to add. Anything else is
            ignored.
        backup: Write <dproj>.bak.<ts> first. Default True. Set False only
            when the caller has already snapshotted the dproj some other
            way (tests, CI).

    Returns:
        (success, message, backup_path) — backup_path is None if no backup
        was written or if there was nothing to do.
    """
    if not missing_classes:
        return True, "Nothing to synthesize.", None

    try:
        with open(dproj_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return False, f"Could not read dproj: {e}", None

    # Find the literal closing tag. Delphi writes it at column ≥4; preserving
    # its leading whitespace keeps the surrounding indentation untouched.
    close_match = re.search(r"^([ \t]*)</Deployment>", text, re.MULTILINE)
    if not close_match:
        return False, (
            "Could not find </Deployment> in the dproj — the project may not "
            "have a Deployment section at all. Open it in the IDE once to "
            "create the section, then retry."
        ), None

    close_indent = close_match.group(1)
    # DeployFile entries sit one level deeper than </Deployment> closing tag,
    # matching the surrounding style.
    entry_indent = close_indent + "    "

    blocks: list[str] = []
    for cls in missing_classes:
        if cls not in _IOS_DEPLOY_SPEC:
            continue
        spec = _IOS_DEPLOY_SPEC[cls]
        suffix = spec["suffix"]
        local_name = os.path.join(
            exe_output_dir_relative, project_name + suffix
        )
        # Always use backslashes in the LocalName — that's what the IDE writes
        # and what RAD Studio's targets expect to parse.
        local_name = local_name.replace("/", "\\")
        blocks.append(_build_deploy_file_xml(
            class_name=cls,
            local_name=local_name,
            config=config,
            platform=platform,
            project_name=project_name,
            indent=entry_indent,
        ))

    if not blocks:
        return True, "Nothing to synthesize.", None

    new_block = "\n".join(blocks) + "\n"
    insertion_point = close_match.start()
    new_text = text[:insertion_point] + new_block + text[insertion_point:]

    backup_path: str | None = None
    if backup:
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_path = f"{dproj_path}.bak.{ts}"
        try:
            shutil.copy2(dproj_path, backup_path)
        except OSError as e:
            return False, f"Could not write backup at {backup_path}: {e}", None

    try:
        with open(dproj_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(new_text)
    except OSError as e:
        return False, f"Could not rewrite dproj: {e}", backup_path

    return True, (
        f"Added {len(blocks)} iOS DeployFile entries to {os.path.basename(dproj_path)} "
        f"(classes: {', '.join(missing_classes)})."
    ), backup_path
