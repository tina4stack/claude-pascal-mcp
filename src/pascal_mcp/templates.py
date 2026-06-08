"""Delphi/Pascal project templates.

Provides embedded templates for creating proper Delphi project structures.
Templates handle the differences between Delphi versions (namespaced vs
non-namespaced units) and project types (VCL GUI, console, FPC).

Usage from MCP tools:
    files = generate_vcl_project("MyApp", "TMainForm", compiler_type="dcc64")
    # Returns dict of {filename: content} ready to write to disk
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# VCL GUI Application Templates
# ---------------------------------------------------------------------------

# Modern Delphi (RAD Studio / dcc64 / dcc32 with namespaced units)
VCL_DPR_MODERN = """\
program {project_name};

uses
  Vcl.Forms,
  {unit_name} in '{unit_name}.pas' {{{form_name}}};

begin
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  Application.CreateForm({form_class}, {form_name});
  Application.Run;
end.
"""

VCL_PAS_MODERN = """\
unit {unit_name};

interface

uses
  Winapi.Windows, Winapi.Messages, System.SysUtils, System.Variants,
  System.Classes, Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs,
  Vcl.StdCtrls;

type
  {form_class} = class(TForm)
{component_declarations}
{event_declarations}
  private
    {{ Private declarations }}
  public
    {{ Public declarations }}
  end;

var
  {form_name}: {form_class};

implementation

{{$R *.dfm}}

{event_implementations}

end.
"""

# Legacy Delphi (Delphi 7 / older dcc32 without namespaced units)
VCL_DPR_LEGACY = """\
program {project_name};

uses
  Forms,
  {unit_name} in '{unit_name}.pas' {{{form_name}}};

begin
  Application.Initialize;
  Application.CreateForm({form_class}, {form_name});
  Application.Run;
end.
"""

VCL_PAS_LEGACY = """\
unit {unit_name};

interface

uses
  Windows, Messages, SysUtils, Variants, Classes, Graphics, Controls,
  Forms, Dialogs, StdCtrls;

type
  {form_class} = class(TForm)
{component_declarations}
{event_declarations}
  private
    {{ Private declarations }}
  public
    {{ Public declarations }}
  end;

var
  {form_name}: {form_class};

implementation

{{$R *.dfm}}

{event_implementations}

end.
"""

# DFM form template (same for all Delphi versions)
VCL_DFM = """\
object {form_name}: {form_class}
  Left = 0
  Top = 0
  Caption = '{form_caption}'
  ClientHeight = {client_height}
  ClientWidth = {client_width}
  Position = poScreenCenter
{component_definitions}
end
"""

# ---------------------------------------------------------------------------
# FMX (FireMonkey) Application Templates — cross-platform, mobile-ready
# ---------------------------------------------------------------------------
#
# FMX differs from VCL in three ways that the generator has to handle:
#   1. uses clause references FMX.* units instead of Vcl.*
#   2. form file is .fmx (slightly different grammar from .dfm — components
#      use Position.X / Position.Y / Size.Width / Size.Height instead of
#      Left / Top / Width / Height, and TLabel uses Text not Caption)
#   3. the IDE's "use SkyBuild" / styling defaults differ — we keep the
#      generated template minimal and styled like a default new FMX app.

FMX_DPR = """\
program {project_name};

// Note: a real FMX app usually has {{$R *.res}} here for the application
// icon/version-info resource. We omit it from the generated template so
// the project compiles standalone without a pre-built .res file. Open
// the project in RAD Studio once and the IDE will regenerate {project_name}.res
// (or set Project → Resources and Images to add an icon).

uses
  System.StartUpCopy,
  FMX.Forms,
  {unit_name} in '{unit_name}.pas' {{{form_name}: {form_class}}};

begin
  Application.Initialize;
  Application.CreateForm({form_class}, {form_name});
  Application.Run;
end.
"""

FMX_PAS = """\
unit {unit_name};

interface

uses
  System.SysUtils, System.Types, System.UITypes, System.Classes,
  System.Variants, FMX.Types, FMX.Controls, FMX.Forms, FMX.Graphics,
  FMX.Dialogs, FMX.StdCtrls, FMX.Controls.Presentation, FMX.Edit,
  FMX.ScrollBox, FMX.Memo, FMX.Memo.Types;

type
  {form_class} = class(TForm)
{component_declarations}
{event_declarations}
  private
    {{ Private declarations }}
  public
    {{ Public declarations }}
  end;

var
  {form_name}: {form_class};

implementation

{{$R *.fmx}}

{event_implementations}

end.
"""

FMX_FMX = """\
object {form_name}: {form_class}
  Left = 0
  Top = 0
  Caption = '{form_caption}'
  ClientHeight = {client_height}
  ClientWidth = {client_width}
  FormFactor.Width = {client_width}
  FormFactor.Height = {client_height}
  FormFactor.Devices = [Desktop, Mobile]
{component_definitions}
end
"""

# FMX component snippets. Coordinates take the same (left, top, width, height)
# inputs as the DFM snippets so callers don't have to re-learn the API —
# they map onto Position.X/Y and Size.Width/Height internally. FMX needs
# float literals everywhere; we emit them as "X.000000000000000000" to
# match what the FMX form designer writes.

FMX_BUTTON = """\
  object {name}: TButton
    Position.X = {left:.6f}
    Position.Y = {top:.6f}
    Size.Width = {width:.6f}
    Size.Height = {height:.6f}
    Size.PlatformDefault = False
    Text = '{caption}'
    TabOrder = {tab_order}
    OnClick = {event_name}
  end"""

FMX_EDIT = """\
  object {name}: TEdit
    Position.X = {left:.6f}
    Position.Y = {top:.6f}
    Size.Width = {width:.6f}
    Size.Height = {height:.6f}
    Size.PlatformDefault = False
    TabOrder = {tab_order}
    Text = '{text}'
  end"""

FMX_LABEL = """\
  object {name}: TLabel
    Position.X = {left:.6f}
    Position.Y = {top:.6f}
    Size.Width = {width:.6f}
    Size.Height = {height:.6f}
    Size.PlatformDefault = False
    Text = '{caption}'
  end"""

FMX_MEMO = """\
  object {name}: TMemo
    Position.X = {left:.6f}
    Position.Y = {top:.6f}
    Size.Width = {width:.6f}
    Size.Height = {height:.6f}
    Size.PlatformDefault = False
    TabOrder = {tab_order}
    Lines.Strings = (
      '')
  end"""


# A minimal but complete .dproj for an FMX application. Targets Win32 + Win64
# + Android64 out of the box (so build_dproj can cross-compile to mobile
# without any manual editing). iOS/macOS are NOT included by default — they
# need PAServer setup and the deploy-manifest synthesizer to be useful.
# Add them later via RAD Studio if needed.
#
# Hand-written XML deliberately. Generated dprojs that go through an
# ElementTree round-trip lose the IDE's attribute ordering and whitespace,
# which RAD Studio tolerates but unsettles version control diffs.
FMX_DPROJ = """\
<?xml version="1.0" encoding="UTF-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
    <PropertyGroup>
        <ProjectGuid>{{{guid}}}</ProjectGuid>
        <ProjectVersion>20.4</ProjectVersion>
        <FrameworkType>FMX</FrameworkType>
        <MainSource>{project_name}.dpr</MainSource>
        <Base>True</Base>
        <Config Condition="'$(Config)'==''">Debug</Config>
        <Platform Condition="'$(Platform)'==''">Win32</Platform>
        <TargetedPlatforms>11</TargetedPlatforms>
        <AppType>Application</AppType>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Config)'=='Base' or '$(Base)'!=''">
        <Base>true</Base>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Cfg_1)'!=''">
        <Cfg_1>true</Cfg_1>
        <CfgParent>Base</CfgParent>
        <Base>true</Base>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Cfg_2)'!=''">
        <Cfg_2>true</Cfg_2>
        <CfgParent>Base</CfgParent>
        <Base>true</Base>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Base)'!=''">
        <DCC_ExeOutput>.\\$(Platform)\\$(Config)</DCC_ExeOutput>
        <DCC_DcuOutput>.\\$(Platform)\\$(Config)</DCC_DcuOutput>
        <DCC_E>false</DCC_E>
        <DCC_F>false</DCC_F>
        <DCC_K>false</DCC_K>
        <DCC_N>false</DCC_N>
        <DCC_S>false</DCC_S>
        <DCC_Namespace>System;Xml;Data;Datasnap;Web;Soap;FMX;$(DCC_Namespace)</DCC_Namespace>
        <DCC_UsePackage>FireDAC;FireDACSqliteDriver;rtl;fmx;DBXSqliteDriver;DBXCommonDriver;DataSnapCommon;DataSnapClient;DataSnapProviderClient;DataSnapServerMidas;IndySystem;DbxCommonDriver;IndyProtocols;IndyCore;IndyIPCommon;CustomIPTransport;FmxTeeUI;FmxTee;TeeDB;Tee;DataSnapFireDAC;tethering;FireDACMSSQLDriver;DBXMSSQLDriver;FireDACADSDriver;FireDACDBXDriver;FireDACIBDriver;FireDACDb2Driver;FireDACPgDriver;FireDACASADriver;FireDACInfDriver;FireDACMySQLDriver;FireDACMongoDBDriver;FireDACOracleDriver;FireDACDSDriver;FireDACODBCDriver;$(DCC_UsePackage)</DCC_UsePackage>
        <DCC_ImageBase>00400000</DCC_ImageBase>
        <SanitizedProjectName>{project_name}</SanitizedProjectName>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Cfg_1)'!=''">
        <DCC_LocalDebugSymbols>false</DCC_LocalDebugSymbols>
        <DCC_Define>RELEASE;$(DCC_Define)</DCC_Define>
        <DCC_SymbolReferenceInfo>0</DCC_SymbolReferenceInfo>
        <DCC_DebugInformation>0</DCC_DebugInformation>
    </PropertyGroup>
    <PropertyGroup Condition="'$(Cfg_2)'!=''">
        <DCC_Define>DEBUG;$(DCC_Define)</DCC_Define>
        <DCC_DebugDCUs>true</DCC_DebugDCUs>
        <DCC_Optimize>false</DCC_Optimize>
        <DCC_GenerateStackFrames>true</DCC_GenerateStackFrames>
    </PropertyGroup>
    <ItemGroup>
        <DelphiCompile Include="$(MainSource)">
            <MainSource>MainSource</MainSource>
        </DelphiCompile>
        <DCCReference Include="{unit_name}.pas">
            <Form>{form_class}</Form>
            <FormType>fmx</FormType>
        </DCCReference>
        <BuildConfiguration Include="Base">
            <Key>Base</Key>
        </BuildConfiguration>
        <BuildConfiguration Include="Release">
            <Key>Cfg_1</Key>
            <CfgParent>Base</CfgParent>
        </BuildConfiguration>
        <BuildConfiguration Include="Debug">
            <Key>Cfg_2</Key>
            <CfgParent>Base</CfgParent>
        </BuildConfiguration>
    </ItemGroup>
    <ProjectExtensions>
        <Borland.Personality>Delphi.Personality.12</Borland.Personality>
        <Borland.ProjectType>Application</Borland.ProjectType>
        <BorlandProject>
            <Delphi.Personality>
                <Source>
                    <Source Name="MainSource">{project_name}.dpr</Source>
                </Source>
            </Delphi.Personality>
            <Platforms>
                <Platform value="Android64">True</Platform>
                <Platform value="Win32">True</Platform>
                <Platform value="Win64">True</Platform>
            </Platforms>
        </BorlandProject>
        <ProjectFileVersion>12</ProjectFileVersion>
    </ProjectExtensions>
    <Import Project="$(BDS)\\Bin\\CodeGear.Delphi.Targets" Condition="Exists('$(BDS)\\Bin\\CodeGear.Delphi.Targets')"/>
    <Import Project="$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj" Condition="Exists('$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj')"/>
    <Import Project="$(MSBuildProjectName).deployproj" Condition="Exists('$(MSBuildProjectName).deployproj')"/>
</Project>
"""


# ---------------------------------------------------------------------------
# Console Application Templates
# ---------------------------------------------------------------------------

CONSOLE_DPR_MODERN = """\
program {project_name};

{{$APPTYPE CONSOLE}}

uses
  System.SysUtils;

begin
  try
{program_body}
  except
    on E: Exception do
      Writeln(E.ClassName, ': ', E.Message);
  end;
end.
"""

CONSOLE_DPR_LEGACY = """\
program {project_name};

{{$APPTYPE CONSOLE}}

uses
  SysUtils;

begin
  try
{program_body}
  except
    on E: Exception do
      Writeln(E.ClassName, ': ', E.Message);
  end;
end.
"""

# ---------------------------------------------------------------------------
# Free Pascal Templates
# ---------------------------------------------------------------------------

FPC_PROGRAM = """\
program {project_name};

{{$mode objfpc}}{{$H+}}

uses
  Classes, SysUtils;

begin
{program_body}
end.
"""

# ---------------------------------------------------------------------------
# Common DFM component snippets
# ---------------------------------------------------------------------------

DFM_BUTTON = """\
  object {name}: TButton
    Left = {left}
    Top = {top}
    Width = {width}
    Height = {height}
    Caption = '{caption}'
    TabOrder = {tab_order}
    OnClick = {event_name}
  end"""

DFM_EDIT = """\
  object {name}: TEdit
    Left = {left}
    Top = {top}
    Width = {width}
    Height = {height}
    TabOrder = {tab_order}
    Text = '{text}'
  end"""

DFM_LABEL = """\
  object {name}: TLabel
    Left = {left}
    Top = {top}
    Width = {width}
    Height = {height}
    Caption = '{caption}'
  end"""

DFM_MEMO = """\
  object {name}: TMemo
    Left = {left}
    Top = {top}
    Width = {width}
    Height = {height}
    TabOrder = {tab_order}
    Lines.Strings = (
      '')
  end"""


# ---------------------------------------------------------------------------
# Template generation helpers
# ---------------------------------------------------------------------------

def _is_legacy_compiler(compiler_type: str | None) -> bool:
    """Check if a compiler type needs legacy (non-namespaced) units.

    Delphi 7 (dcc32 from Borland path) uses non-namespaced units.
    Modern RAD Studio versions use namespaced units (Vcl.*, System.*, etc.).
    """
    if compiler_type is None:
        return False
    ct = compiler_type.lower()
    # If it's a path containing "borland" or "delphi7", it's legacy
    if "borland" in ct or "delphi7" in ct or "delphi 7" in ct:
        return True
    return False


def generate_vcl_project(
    project_name: str = "Project1",
    form_name: str = "Form1",
    form_class: str = "TForm1",
    form_caption: str = "My Application",
    unit_name: str = "uMain",
    client_width: int = 400,
    client_height: int = 300,
    components: list[dict] | None = None,
    events: list[dict] | None = None,
    compiler_type: str | None = None,
) -> dict[str, str]:
    """Generate a complete VCL GUI application project.

    Args:
        project_name: Name for the .dpr file (without extension).
        form_name: Variable name of the main form (e.g. 'Form1').
        form_class: Class name of the main form (e.g. 'TForm1').
        form_caption: Title bar text.
        unit_name: Name for the main unit file (without extension).
        client_width: Form client area width in pixels.
        client_height: Form client area height in pixels.
        components: List of component dicts with keys like:
            {"type": "TButton", "name": "btnOK", "left": 10, "top": 10,
             "width": 75, "height": 25, "caption": "OK", "event": "btnOKClick"}
        events: List of event handler dicts with keys:
            {"name": "btnOKClick", "body": "ShowMessage('OK clicked');"}
        compiler_type: Compiler type/path to determine legacy vs modern units.

    Returns:
        Dict mapping filenames to their content.
    """
    legacy = _is_legacy_compiler(compiler_type)
    components = components or []
    events = events or []

    # Build component declarations for the .pas type block
    comp_decls = []
    for comp in components:
        comp_decls.append(f"    {comp['name']}: {comp['type']};")

    # Build event declarations
    event_decls = []
    for evt in events:
        event_decls.append(f"    procedure {evt['name']}(Sender: TObject);")

    # Build event implementations
    event_impls = []
    for evt in events:
        body = evt.get("body", "  // TODO")
        event_impls.append(
            f"procedure {form_class}.{evt['name']}(Sender: TObject);\n"
            f"begin\n"
            f"  {body}\n"
            f"end;\n"
        )

    # Build DFM component definitions
    dfm_comps = []
    tab_order = 0
    for comp in components:
        ctype = comp["type"]
        if ctype == "TButton":
            dfm_comps.append(DFM_BUTTON.format(
                name=comp["name"],
                left=comp.get("left", 10),
                top=comp.get("top", 10),
                width=comp.get("width", 75),
                height=comp.get("height", 25),
                caption=comp.get("caption", comp["name"]),
                tab_order=tab_order,
                event_name=comp.get("event", f"{comp['name']}Click"),
            ))
            tab_order += 1
        elif ctype == "TEdit":
            dfm_comps.append(DFM_EDIT.format(
                name=comp["name"],
                left=comp.get("left", 10),
                top=comp.get("top", 10),
                width=comp.get("width", 121),
                height=comp.get("height", 21),
                tab_order=tab_order,
                text=comp.get("text", ""),
            ))
            tab_order += 1
        elif ctype == "TLabel":
            dfm_comps.append(DFM_LABEL.format(
                name=comp["name"],
                left=comp.get("left", 10),
                top=comp.get("top", 10),
                width=comp.get("width", 50),
                height=comp.get("height", 13),
                caption=comp.get("caption", comp["name"]),
            ))
        elif ctype == "TMemo":
            dfm_comps.append(DFM_MEMO.format(
                name=comp["name"],
                left=comp.get("left", 10),
                top=comp.get("top", 10),
                width=comp.get("width", 200),
                height=comp.get("height", 100),
                tab_order=tab_order,
            ))
            tab_order += 1

    # Format template variables
    fmt = {
        "project_name": project_name,
        "form_name": form_name,
        "form_class": form_class,
        "form_caption": form_caption,
        "unit_name": unit_name,
        "client_width": client_width,
        "client_height": client_height,
        "component_declarations": "\n".join(comp_decls) if comp_decls else "    { no components }",
        "event_declarations": "\n".join(event_decls) if event_decls else "",
        "event_implementations": "\n".join(event_impls),
        "component_definitions": "\n".join(dfm_comps),
    }

    # Select templates based on compiler version
    dpr_tmpl = VCL_DPR_LEGACY if legacy else VCL_DPR_MODERN
    pas_tmpl = VCL_PAS_LEGACY if legacy else VCL_PAS_MODERN

    return {
        f"{project_name}.dpr": dpr_tmpl.format(**fmt),
        f"{unit_name}.pas": pas_tmpl.format(**fmt),
        f"{unit_name}.dfm": VCL_DFM.format(**fmt),
    }


def generate_fmx_project(
    project_name: str = "Project1",
    form_name: str = "Form1",
    form_class: str = "TForm1",
    form_caption: str = "My FMX Application",
    unit_name: str = "uMain",
    client_width: int = 320,
    client_height: int = 480,
    components: list[dict] | None = None,
    events: list[dict] | None = None,
    compiler_type: str | None = None,
    include_dproj: bool = True,
) -> dict[str, str]:
    """Generate a complete FMX (FireMonkey) application project.

    FMX is the cross-platform UI framework that lets a single source tree
    target Win32 / Win64 / Android / iOS / macOS / Linux. This generator
    produces a project that the IDE recognises as a real FMX app — same
    .dproj structure (TargetedPlatforms, FrameworkType=FMX, Platforms
    section) the IDE writes, so build_dproj on the result will cross-
    compile to Android out of the box.

    The component input format is the same as generate_vcl_project() —
    callers pass (left, top, width, height) and we map them to FMX's
    Position.X / Position.Y / Size.Width / Size.Height internally.

    Args:
        project_name: Name for the .dpr file (without extension).
        form_name: Variable name of the main form (e.g. 'Form1').
        form_class: Class name of the main form (e.g. 'TForm1').
        form_caption: Title bar text.
        unit_name: Name for the main unit file (without extension).
        client_width: Form width in dips (defaults to 320 — phone-portrait).
        client_height: Form height in dips (defaults to 480).
        components: List of component dicts with the same shape as
            generate_vcl_project. Supported types: TButton, TEdit, TLabel,
            TMemo.
        events: List of event handler dicts: {"name": ..., "body": ...}.
        compiler_type: Compiler type/path. FMX requires modern namespaced
            units; legacy Delphi 7 cannot build FMX. Passed through but
            doesn't change templates (FMX templates are always namespaced).
        include_dproj: When True (default), emits a .dproj alongside the
            source files so build_dproj can build the project for
            Win32/Win64/Android64 without manual editing. When False,
            only emits .dpr/.pas/.fmx — for callers that just need the
            source to feed into compile_pascal.

    Returns:
        Dict mapping filenames to their content. Always includes
        <project_name>.dpr, <unit_name>.pas, <unit_name>.fmx; optionally
        includes <project_name>.dproj.
    """
    components = components or []
    events = events or []

    comp_decls = [f"    {c['name']}: {c['type']};" for c in components]
    event_decls = [
        f"    procedure {e['name']}(Sender: TObject);" for e in events
    ]
    event_impls = []
    for evt in events:
        body = evt.get("body", "  // TODO")
        event_impls.append(
            f"procedure {form_class}.{evt['name']}(Sender: TObject);\n"
            f"begin\n"
            f"  {body}\n"
            f"end;\n"
        )

    fmx_comps = []
    tab_order = 0
    for comp in components:
        ctype = comp["type"]
        common = {
            "name": comp["name"],
            "left": float(comp.get("left", 10)),
            "top": float(comp.get("top", 10)),
            "width": float(comp.get("width", 75)),
            "height": float(comp.get("height", 25)),
            "tab_order": tab_order,
        }
        if ctype == "TButton":
            fmx_comps.append(FMX_BUTTON.format(
                **common,
                caption=comp.get("caption", comp["name"]),
                event_name=comp.get("event", f"{comp['name']}Click"),
            ))
            tab_order += 1
        elif ctype == "TEdit":
            fmx_comps.append(FMX_EDIT.format(
                **common,
                text=comp.get("text", ""),
            ))
            tab_order += 1
        elif ctype == "TLabel":
            # TLabel doesn't take a tab order; FMX_LABEL template ignores it
            fmx_comps.append(FMX_LABEL.format(
                **common,
                caption=comp.get("caption", comp["name"]),
            ))
        elif ctype == "TMemo":
            fmx_comps.append(FMX_MEMO.format(**common))
            tab_order += 1

    fmt = {
        "project_name": project_name,
        "form_name": form_name,
        "form_class": form_class,
        "form_caption": form_caption,
        "unit_name": unit_name,
        "client_width": client_width,
        "client_height": client_height,
        "component_declarations": "\n".join(comp_decls) if comp_decls else "    {{ no components }}",
        "event_declarations": "\n".join(event_decls),
        "event_implementations": "\n".join(event_impls),
        "component_definitions": "\n".join(fmx_comps),
    }

    files = {
        f"{project_name}.dpr": FMX_DPR.format(**fmt),
        f"{unit_name}.pas": FMX_PAS.format(**fmt),
        f"{unit_name}.fmx": FMX_FMX.format(**fmt),
    }

    if include_dproj:
        import uuid
        # GUID is generated fresh per project so two checked-in dprojs can't
        # collide in the IDE's recently-used list.
        fmt_with_guid = {**fmt, "guid": str(uuid.uuid4()).upper()}
        files[f"{project_name}.dproj"] = FMX_DPROJ.format(**fmt_with_guid)

    return files


def generate_console_project(
    project_name: str = "Project1",
    program_body: str = "    Writeln('Hello, World!');",
    compiler_type: str | None = None,
) -> dict[str, str]:
    """Generate a console application project.

    Args:
        project_name: Name for the .dpr file (without extension).
        program_body: The Pascal code to put in the main begin..end block.
            Each line should be indented with 4 spaces.
        compiler_type: Compiler type/path to determine legacy vs modern units.

    Returns:
        Dict mapping filenames to their content.
    """
    legacy = _is_legacy_compiler(compiler_type)
    tmpl = CONSOLE_DPR_LEGACY if legacy else CONSOLE_DPR_MODERN

    return {
        f"{project_name}.dpr": tmpl.format(
            project_name=project_name,
            program_body=program_body,
        ),
    }


def generate_fpc_project(
    project_name: str = "Project1",
    program_body: str = "  Writeln('Hello, World!');",
) -> dict[str, str]:
    """Generate a Free Pascal project.

    Args:
        project_name: Name for the .pas file (without extension).
        program_body: The Pascal code for the main begin..end block.

    Returns:
        Dict mapping filenames to their content.
    """
    return {
        f"{project_name}.pas": FPC_PROGRAM.format(
            project_name=project_name,
            program_body=program_body,
        ),
    }
