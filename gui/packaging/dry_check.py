"""Windows packaging checklist that does not build the exe and does not need a game install.

    python gui/packaging/dry_check.py
    python gui/packaging/dry_check.py --app dist/DeckBench

The default mode checks the git tree against build.ps1's staging rules and
gui/packaging/ship-manifest.txt. ``--app`` applies the same manifest to an
already-built folder (file presence and the mentor.local.json doc pointer).
Game-file hashing stays in audit.ps1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

# Surfaces the 0.1.5 package must stage. ship-manifest.txt can list more;
# deleting one of these fails the dry-check even if audit.ps1 is not re-run.
REQUIRED_PATHS = (
    "sim/tools/import_run.py",
    "sim/tools/seed_preview.py",
    "sim/tools/import_dll_mod.py",
    "sim/sts2sim/dllmod/__init__.py",
    "sim/sts2sim/dllmod/__main__.py",
    "sim/sts2sim/dllmod/extract.py",
    "sim/sts2sim/dllmod/metadata.py",
    "sim/sts2sim/dllmod/package.py",
    "sim/sts2sim/saveimport.py",
    "sim/sts2sim/engine/seedpreview.py",
    "sim/sts2sim/engine/mentor_paths.py",
    "sim/gui/server.py",
    "sim/gui/modeditor.py",
    "sim/gui/worker.py",
    "sim/gui/backend.py",
    "sim/gui/i18n.py",
    "sim/gui/demo.py",
    "sim/gui/demo/sample.deckbench.zip",
    "app/README.txt",
    "app/decompiler/ilspycmd-host.exe",
)
POINTER_PATHS = (
    "app/README.txt",
    "sim/gui/locales/en.json",
    "sim/gui/locales/zhs.json",
    "sim/gui/locales/ja.json",
    "sim/gui/locales/ko.json",
)
# Vue pages are compiled into gui/web/dist. They must stay in git and must not
# be copied into sim/ as source (build.ps1 skips gui/web).
FRONTEND_PAGES = (
    "gui/web/src/pages/ImportRun.vue",
    "gui/web/src/pages/SeedPreview.vue",
    "gui/web/src/pages/ModEditor.vue",
    "gui/web/src/pages/ExplainLog.vue",
    "gui/web/src/pages/Calibrate.vue",
    "gui/web/src/pages/Compare.vue",
    "gui/web/src/pages/Decks.vue",
    "gui/web/src/pages/WhatsNew.vue",
)
DECOMPILER_SOURCES = (
    "gui/packaging/decompiler/Program.cs",
    "gui/packaging/decompiler/ilspycmd-host.csproj",
)
CODEX_NAME = re.compile(
    r"^(eng|zhs)_(cards|monsters|relics|powers|potions|encounters|characters|acts)\.json$"
)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_build_rules(text):
    """Return (include prefixes, gui/ directory names build.ps1 does not stage)."""
    inc = re.search(r"-match '\^\(([^)]+)\)/'", text)
    skip = re.search(r"-notmatch '\^gui/\(([^)]+)\)/'", text)
    if not inc or not skip:
        raise ValueError("build.ps1 staging regex not found")
    return inc.group(1).split("|"), skip.group(1).split("|")


def would_stage(path, prefixes, gui_skips):
    if any(path == p or path.startswith(p + "/") for p in prefixes):
        return True
    if path.startswith("gui/"):
        for skip in gui_skips:
            if path == f"gui/{skip}" or path.startswith(f"gui/{skip}/"):
                return False
        return True
    return False


def load_manifest(text):
    entries = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        path, flags = parts[0], parts[1:]
        if not (path.startswith("sim/") or path.startswith("app/")):
            raise ValueError(f"bad ship-manifest path: {path}")
        if any(flag != "pointer" for flag in flags):
            raise ValueError(f"bad ship-manifest flag on {path}: {flags}")
        entries.append((path, "pointer" in flags))
    if not entries:
        raise ValueError("ship-manifest.txt is empty")
    return entries


def pointer_problems(label, text):
    bad = []
    if "mentor.local.json" not in text:
        bad.append(f"missing mentor.local.json pointer :: {label}")
    if "docs/DEVELOPER.md" not in text:
        bad.append(f"missing docs/DEVELOPER.md pointer :: {label}")
    return bad


def app_presence_errors(app, entries, allow_missing_decompiler=False):
    """Same file-presence rules as audit.ps1, for a built DeckBench directory."""
    bad = []
    for path, pointer in entries:
        rel = path[len("app/"):] if path.startswith("app/") else path
        if allow_missing_decompiler and rel.endswith("ilspycmd-host.exe"):
            continue
        full = os.path.join(app, *rel.split("/"))
        if not os.path.isfile(full):
            bad.append(f"missing required :: {path}")
            continue
        if pointer:
            bad.extend(pointer_problems(path, _read(full)))
    return bad


def forbidden_names(audit_text):
    m = re.search(r"\$names = @\((.*?)\)", audit_text, re.S)
    if not m:
        raise ValueError("audit.ps1 $names list not found")
    names = re.findall(r"'([^']+)'", m.group(1))
    if "mentor.local.json" not in names:
        raise ValueError("audit.ps1 no longer forbids mentor.local.json")
    return names


def forbidden_extensions(audit_text):
    m = re.search(r"\$f\.Extension -in ([^\n]+)", audit_text)
    if not m:
        raise ValueError("audit.ps1 extension blacklist not found")
    exts = re.findall(r"'(\.[A-Za-z0-9]+)'", m.group(1))
    if not {".cs", ".pck", ".onnx", ".csproj"} <= set(exts):
        raise ValueError(f"audit.ps1 extension blacklist drifted: {exts}")
    return exts


def forbidden_folders(audit_text):
    m = re.search(r"\\\\\(([^)]*)\)\\\\", audit_text)
    if not m:
        raise ValueError("audit.ps1 forbidden-folder regex not found")
    literals = []
    for part in m.group(1).split("|"):
        if "\\" in part or "[" in part:
            continue
        literals.append(part)
    if "seed-preview" not in literals or "decompiled" not in literals:
        raise ValueError(f"audit.ps1 folder blacklist drifted: {literals}")
    if "decompiler" in literals:
        raise ValueError("audit.ps1 would reject the shipped decompiler folder")
    return literals


def _read(path):
    # utf-8-sig drops a leading BOM so a packaging script saved for
    # Windows PowerShell 5.1 still matches the text checks below.
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


UTF8_BOM = b"\xef\xbb\xbf"


def ps1_encoding_problems(data, label):
    """Windows PowerShell 5.1 reads a BOM-less script as the ANSI code page.

    UTF-8 Chinese is three bytes. Decoded as a double-byte code page, the
    leftover byte pairs with the next ASCII character and can swallow a
    quote. A UTF-8 BOM makes 5.1 decode the file as UTF-8. Pure ASCII is
    safe without a BOM.
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return [f"{label} is UTF-16; save it as UTF-8 with BOM or pure ASCII"]
    bom = data.startswith(UTF8_BOM)
    body = data[len(UTF8_BOM):] if bom else data
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as e:
        return [f"{label} is not valid UTF-8: {e}"]
    if any(ord(ch) > 127 for ch in text) and not bom:
        return [(
            f"{label} has non-ASCII text but no UTF-8 BOM; "
            "Windows PowerShell 5.1 would read it as ANSI and can swallow a quote"
        )]
    return []


def powershell_encoding_problems(root):
    """Every .ps1 with non-ASCII text must be UTF-8 with a BOM."""
    bad = []
    found = False
    skip = {".git", ".venv", "node_modules", "__pycache__"}
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in skip]
        for name in files:
            if not name.lower().endswith(".ps1"):
                continue
            found = True
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace("\\", "/")
            with open(path, "rb") as handle:
                bad.extend(ps1_encoding_problems(handle.read(), rel))
    if not found:
        bad.append("no .ps1 files found")
    return bad


def _git_files(root):
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        check=True, capture_output=True,
    )
    return [p.decode("utf-8") for p in out.stdout.split(b"\0") if p]


PROJECT_XML_SUFFIXES = (".csproj", ".props", ".targets", ".xml")
_XML_COMMENT = re.compile(r"<!--(.*?)-->", re.S)


def xml_comment_problems(text):
    """MSBuild MSB4025: a comment cannot contain '--' or end with '-'."""
    bad = []
    for match in _XML_COMMENT.finditer(text):
        body = match.group(1)
        if "--" in body:
            bad.append("XML comment contains '--'")
        if body.endswith("-"):
            bad.append("XML comment ends with '-'")
    return bad


def packaging_project_xml_problems(root):
    """Every packaging csproj/props/targets/xml file must load, comments included."""
    packaging = os.path.join(root, "gui", "packaging")
    bad = []
    found = False
    for dirpath, _dirs, files in os.walk(packaging):
        for name in files:
            if os.path.splitext(name)[1].lower() not in PROJECT_XML_SUFFIXES:
                continue
            found = True
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace("\\", "/")
            text = _read(path)
            try:
                ET.fromstring(text)
            except ET.ParseError as e:
                bad.append(f"packaging project XML is not loadable: {rel}: {e}")
                continue
            for item in xml_comment_problems(text):
                bad.append(f"{item} (MSBuild MSB4025): {rel}")
    if not found:
        bad.append("no packaging csproj, props, targets, or xml files found")
    return bad


def check(root=None):
    """Return a list of problems. Empty means the tree is ready to pack."""
    root = root or repo_root()
    bad = []
    packaging = os.path.join(root, "gui", "packaging")
    build_text = _read(os.path.join(packaging, "build.ps1"))
    audit_text = _read(os.path.join(packaging, "audit.ps1"))
    spec_text = _read(os.path.join(packaging, "DeckBench.spec"))
    try:
        prefixes, gui_skips = parse_build_rules(build_text)
        entries = load_manifest(_read(os.path.join(packaging, "ship-manifest.txt")))
        names = forbidden_names(audit_text)
        exts = forbidden_extensions(audit_text)
        folders = forbidden_folders(audit_text)
        files = _git_files(root)
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        return [str(e)]

    staged = [f for f in files if would_stage(f, prefixes, gui_skips)]
    by_path = {path: pointer for path, pointer in entries}

    for path in REQUIRED_PATHS:
        if path not in by_path:
            bad.append(f"ship-manifest.txt missing {path}")
    for path in POINTER_PATHS:
        if not by_path.get(path):
            bad.append(f"ship-manifest.txt missing pointer flag on {path}")

    for path, pointer in entries:
        if not path.startswith("sim/"):
            continue
        repo_rel = path[len("sim/"):]
        if repo_rel not in staged:
            bad.append(f"not staged into sim/: {repo_rel}")
        elif pointer:
            bad.extend(pointer_problems(path, _read(os.path.join(root, repo_rel))))

    readme = os.path.join(packaging, "README-win.txt")
    if os.path.isfile(readme):
        bad.extend(pointer_problems("gui/packaging/README-win.txt", _read(readme)))
    else:
        bad.append("missing gui/packaging/README-win.txt")
    if 'Copy-Item (Join-Path $PSScriptRoot "README-win.txt")' not in build_text:
        bad.append("build.ps1 does not copy README-win.txt into the app")

    for rel in DECOMPILER_SOURCES:
        if not os.path.isfile(os.path.join(root, rel)):
            bad.append(f"missing decompiler source: {rel}")
        if rel in staged:
            bad.append(f"decompiler source would be staged into sim/: {rel}")
    csproj = os.path.join(root, "gui", "packaging", "decompiler", "ilspycmd-host.csproj")
    if os.path.isfile(csproj) and "<AssemblyName>ilspycmd-host</AssemblyName>" not in _read(csproj):
        bad.append("decompiler project AssemblyName is not ilspycmd-host")
    if "ilspycmd-host.exe" not in build_text or 'Join-Path $app "decompiler"' not in build_text:
        bad.append("build.ps1 does not copy the published decompiler next to the exe")

    for rel in FRONTEND_PAGES:
        if rel not in files:
            bad.append(f"frontend page is not tracked: {rel}")
        if rel in staged:
            bad.append(f"frontend source would be staged into sim/: {rel}")
    if "npm.cmd run build" not in build_text or "gui\\web\\dist" not in build_text:
        bad.append("build.ps1 does not build and copy gui/web/dist")
    if "gui_web" not in spec_text:
        bad.append("DeckBench.spec does not bundle gui/web/dist as gui_web")
    if "sample.deckbench.zip" not in spec_text:
        bad.append("DeckBench.spec does not bundle the demo sample")
    for hidden in ("dnfile", "pefile"):
        if f'"{hidden}"' not in spec_text:
            bad.append(f"DeckBench.spec missing hiddenimport {hidden} (dllmod metadata)")

    if "ls-files" not in build_text:
        bad.append("build.ps1 no longer stages via git ls-files")
    if re.search(r"Copy-Item[^\r\n]*mentor\.local\.json", build_text):
        bad.append("build.ps1 copies mentor.local.json")
    dev_doc = os.path.join(root, "docs", "DEVELOPER.md")
    if not os.path.isfile(dev_doc) or "mentor.local.json" not in _read(dev_doc):
        bad.append("docs/DEVELOPER.md is missing the mentor.local.json instructions")

    for needle in (
        "ship-manifest.txt",
        "AllowMissingDecompiler",
        "missing mentor.local.json pointer",
        "missing docs/DEVELOPER.md pointer",
        "spire-mentor checkout",
        "binary inside sim",
        "sts2_rs",
        "sts2_hint",
        "champions.toml",
    ):
        if needle not in audit_text:
            bad.append(f"audit.ps1 missing check: {needle}")

    if "mentor.local.json" in files:
        bad.append("mentor.local.json is git-tracked")

    for rel in staged:
        base = os.path.basename(rel)
        if base in names or base == "champions.toml" or CODEX_NAME.match(base):
            bad.append(f"staged file is forbidden: {rel}")
        ext = os.path.splitext(rel)[1].lower()
        if ext in exts or ext in (".dll", ".exe"):
            bad.append(f"staged file has a forbidden extension: {rel}")
        parts = rel.split("/")
        if any(p in folders or p in ("sts2_rs", "sts2_hint", "mentor") for p in parts):
            bad.append(f"staged path uses a forbidden folder: {rel}")

    bad.extend(_version_problems(root, build_text, spec_text))
    bad.extend(packaging_project_xml_problems(root))
    bad.extend(powershell_encoding_problems(root))
    return bad


def project_version(root):
    """The only version literal is sts2sim.__version__. Callers compare other copies to it."""
    sys.path.insert(0, root)
    from sts2sim.version import read_project_version
    return read_project_version(root)


def _version_problems(root, build_text, spec_text):
    bad = []
    try:
        version = project_version(root)
    except (OSError, ValueError) as exc:
        return [str(exc)]
    if re.search(r"""\[string\]\$Version\s*=\s*["']\d""", build_text):
        bad.append("build.ps1 hardcodes -Version; read sts2sim.__version__ instead")
    if "read_version.py" not in build_text or "__version__" not in build_text:
        bad.append("build.ps1 does not read sts2sim.__version__")
    if "DeckBench-$Version-win64.zip" not in build_text:
        bad.append("build.ps1 zip name does not use the project version")
    if "write_version_info.py" not in build_text or "file_version_info.txt" not in build_text:
        bad.append("build.ps1 does not write the Windows file version resource")
    if "file_version_info.txt" not in spec_text or '["version"]' not in spec_text:
        bad.append("DeckBench.spec does not embed file_version_info.txt on Windows")
    pkg = json.loads(_read(os.path.join(root, "gui", "web", "package.json")))
    if pkg.get("version") != version:
        bad.append(f"gui/web/package.json version is not {version}")
    lock = json.loads(_read(os.path.join(root, "gui", "web", "package-lock.json")))
    locked = lock.get("version")
    locked_root = (lock.get("packages") or {}).get("", {}).get("version")
    if locked != version or locked_root != version:
        bad.append(f"gui/web/package-lock.json version is not {version}")
    dev = _read(os.path.join(root, "docs", "DEVELOPER.md"))
    if f"DeckBench-{version}-win64.zip" not in dev:
        bad.append(f"docs/DEVELOPER.md packaging commands are not {version}")
    if "sts2sim.__version__" not in dev or "read_version.py" not in dev:
        bad.append("docs/DEVELOPER.md does not read the package version from sts2sim.__version__")
    if "-Version 0.1.3" in dev or "DeckBench-0.1.3" in dev:
        bad.append("docs/DEVELOPER.md still shows the 0.1.3 packaging commands")
    workflow = _read(os.path.join(root, ".github", "workflows", "windows-package.yml"))
    if "read_version.py" not in workflow:
        bad.append("windows-package.yml does not read sts2sim.__version__")
    if re.search(r"PACKAGE_VERSION:\s*[\"']\d", workflow):
        bad.append("windows-package.yml hardcodes PACKAGE_VERSION")
    for flag in ("-p:Version=", "-p:FileVersion=", "-p:AssemblyVersion=", "-p:InformationalVersion="):
        if flag not in workflow:
            bad.append(f"windows-package.yml does not stamp {flag}")
    csproj = _read(os.path.join(root, "gui", "packaging", "decompiler", "ilspycmd-host.csproj"))
    if re.search(r"<Version>\s*[0-9]", csproj):
        bad.append("decompiler csproj hardcodes Version; stamp it at publish")
    if "IncludeSourceRevisionInInformationalVersion" not in csproj:
        bad.append("decompiler csproj should keep InformationalVersion free of a git suffix")
    smoke = _read(os.path.join(root, "gui", "packaging", "smoke_api.ps1"))
    if "/api/version" not in smoke:
        bad.append("smoke_api.ps1 does not assert GET /api/version")
    if re.search(r"""ExpectedVersion\s*=\s*["']\d""", smoke):
        bad.append("smoke_api.ps1 hardcodes ExpectedVersion")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", help="built DeckBench directory to check for ship-manifest files")
    ap.add_argument("--allow-missing-decompiler", action="store_true",
                    help="with --app, do not require decompiler/ilspycmd-host.exe")
    args = ap.parse_args(argv)
    root = repo_root()
    bad = check(root)
    if args.app:
        app = args.app if os.path.isabs(args.app) else os.path.join(root, args.app)
        try:
            entries = load_manifest(_read(os.path.join(root, "gui", "packaging", "ship-manifest.txt")))
        except (OSError, ValueError) as e:
            bad.append(str(e))
            entries = []
        bad.extend(app_presence_errors(app, entries, args.allow_missing_decompiler))
    if bad:
        print(f"FAIL ({len(bad)})")
        for item in bad:
            print(f" - {item}")
        return 1
    try:
        stamped = project_version(root)
    except (OSError, ValueError):
        stamped = "?"
    print(
        f"PASS: {stamped} packaging manifest matches git "
        "(import_run, seed_preview, dllmod, decompiler project, mentor.local.json docs pointer)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
