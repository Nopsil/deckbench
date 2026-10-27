"""Windows packaging checklist. No PyInstaller, no game install, no built exe."""
import importlib.util
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "gui", "packaging", "dry_check.py")


def _load():
    spec = importlib.util.spec_from_file_location("deckbench_dry_check", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_packaging_dry_check_cli():
    r = subprocess.run([sys.executable, SCRIPT], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "PASS" in r.stdout


def test_stage_rules_keep_tools_and_skip_packaging_sources():
    mod = _load()
    build = open(os.path.join(ROOT, "gui", "packaging", "build.ps1"), encoding="utf-8").read()
    prefixes, skips = mod.parse_build_rules(build)
    assert prefixes == ["sts2sim", "mods", "tools", "data", "experiments"]
    assert skips == ["packaging", "web"]
    for rel in (
        "tools/import_run.py",
        "tools/seed_preview.py",
        "tools/import_dll_mod.py",
        "sts2sim/dllmod/package.py",
        "sts2sim/saveimport.py",
        "sts2sim/engine/seedpreview.py",
        "sts2sim/engine/mentor_paths.py",
        "gui/server.py",
        "gui/modeditor.py",
        "gui/locales/en.json",
    ):
        assert mod.would_stage(rel, prefixes, skips), rel
    for rel in (
        "gui/packaging/decompiler/Program.cs",
        "gui/packaging/launcher.py",
        "gui/web/src/pages/SeedPreview.vue",
        "gui/web/src/pages/ImportRun.vue",
        "tests/fixtures/dllmod/SyntheticMod.cs",
        "docs/DEVELOPER.md",
    ):
        assert not mod.would_stage(rel, prefixes, skips), rel


def test_pointer_checker_rejects_text_without_the_doc():
    mod = _load()
    assert mod.pointer_problems("README.txt", "put mentor.local.json next to the exe")
    assert mod.pointer_problems("README.txt", "see docs/DEVELOPER.md")
    assert mod.pointer_problems("README.txt", "mentor.local.json\ndocs/DEVELOPER.md") == []


def test_app_presence_requires_tools_decompiler_and_pointer(tmp_path):
    mod = _load()
    manifest = open(os.path.join(ROOT, "gui", "packaging", "ship-manifest.txt"), encoding="utf-8").read()
    entries = mod.load_manifest(manifest)
    app = tmp_path / "DeckBench"

    def write(rel, text="x"):
        path = app.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    pointer = "mentor.local.json\ndocs/DEVELOPER.md\n"
    for path, is_pointer in entries:
        rel = path[len("app/"):] if path.startswith("app/") else path
        write(rel, pointer if is_pointer else "x")

    assert mod.app_presence_errors(str(app), entries) == []

    os.remove(app / "sim" / "tools" / "import_run.py")
    missing = mod.app_presence_errors(str(app), entries)
    assert any("import_run.py" in item for item in missing)

    write("sim/tools/import_run.py", "x")
    os.remove(app / "decompiler" / "ilspycmd-host.exe")
    assert any("ilspycmd-host.exe" in item for item in mod.app_presence_errors(str(app), entries))
    assert mod.app_presence_errors(str(app), entries, allow_missing_decompiler=True) == []

    write("decompiler/ilspycmd-host.exe", "x")
    write("README.txt", "no config here")
    pointed = mod.app_presence_errors(str(app), entries)
    assert any("mentor.local.json" in item for item in pointed)
    assert any("docs/DEVELOPER.md" in item for item in pointed)
