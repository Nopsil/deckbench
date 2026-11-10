"""Run the mod-author guide's example commands on examples/spark.

The bash blocks in docs/MOD_AUTHORS.md and docs/MOD_AUTHORS.zh-CN.md are the
commands. A block tagged needs-game needs a local game install and is skipped.
The rest run on the internal Python fight engine with the tiny samples written
in the guide. No game files are read or written.
"""
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EN = os.path.join(ROOT, "docs", "MOD_AUTHORS.md")
ZH = os.path.join(ROOT, "docs", "MOD_AUTHORS.zh-CN.md")
FENCE = re.compile(r"```([^\n]*)\n(.*?)```", re.S)
GAME_ONLY = ("tools/batch.py", "tools/ab_card.py", "sts2sim.gamedata", "gui.app")


def fences(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for m in FENCE.finditer(text):
        info = m.group(1).strip()
        if info == "bash" or info.startswith("bash "):
            out.append((info, m.group(2).strip("\n") + "\n"))
    return out


def test_both_guides_use_the_same_commands():
    en, zh = fences(EN), fences(ZH)
    assert en and zh
    assert [info for info, _ in en] == [info for info, _ in zh]
    assert [body for _, body in en] == [body for _, body in zh]
    assert any("needs-game" in info.split() for info, _ in en)
    for path in (EN, ZH):
        text = open(path, encoding="utf-8").read()
        assert "tests/test_mod_authors.py" in text
        assert "needs-game" in text
        assert "--workers" in text and "--explain" in text and "--mechanic-aware" in text
        assert "explain_fight.py" in text and "Wilson" in text


def test_example_mod_is_yaml_only():
    spark = os.path.join(ROOT, "examples", "spark")
    names = []
    for dirpath, _dirs, files in os.walk(spark):
        for name in files:
            path = os.path.join(dirpath, name)
            assert os.path.splitext(name)[1] in {".yaml", ".yml"}, path
            names.append(name)
            raw = open(path, encoding="utf-8").read()
            assert "\x00" not in raw
    assert {"mod.yaml", "cards.yaml", "decks.yaml", "winrate.yaml", "ab.yaml"} <= set(names)


def test_readme_links_the_guide():
    for name in ("README.md", "README.en.md", "README.ja.md", "README.ko.md"):
        text = open(os.path.join(ROOT, name), encoding="utf-8").read()
        assert "docs/MOD_AUTHORS.md" in text
        assert "MOD_AUTHORS.zh-CN.md" in text


def _bash_executable():
    """Interpreter for the guide's bash blocks.

    On Windows, ``bash`` on PATH is the WSL stub. It exits with
    "Windows Subsystem for Linux has no installed distributions" and does
    not run the script. Git Bash does. Return None when that install is
    missing so the caller can skip instead of calling the stub.
    """
    if os.name != "nt":
        return "bash"
    candidates = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        root = os.environ.get(key)
        if not root:
            continue
        candidates.append(os.path.join(root, "Git", "bin", "bash.exe"))
        candidates.append(os.path.join(root, "Git", "usr", "bin", "bash.exe"))
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        lowered = directory.replace("/", "\\").lower()
        if lowered.endswith(("\\system32", "\\syswow64")):
            continue
        if "\\windowsapps" in lowered:
            continue
        for name in ("bash.exe", "bash"):
            candidates.append(os.path.join(directory, name))
    seen = set()
    for path in candidates:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(path):
            return path
    return None


def test_guide_commands_run_with_tiny_samples(tmp_path):
    blocks = fences(EN)
    skipped = [body for info, body in blocks if "needs-game" in info.split()]
    runnable = [body for info, body in blocks if "needs-game" not in info.split()]
    assert len(skipped) >= 2 and runnable
    skipped_text = "\n".join(skipped)
    assert "tools/batch.py" in skipped_text
    assert "tools/ab_card.py" in skipped_text
    assert "sts2sim.gamedata" in skipped_text
    for body in runnable:
        for token in GAME_ONLY:
            assert token not in body

    bash = _bash_executable()
    if bash is None:
        pytest.skip(
            "Git Bash was not found. On Windows, `bash` is the WSL stub "
            "and reports that Windows Subsystem for Linux has no installed "
            "distributions, so it cannot run this guide script."
        )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    os.symlink(sys.executable, bindir / "python")
    if os.name == "nt":
        os.symlink(sys.executable, bindir / "python.exe")
    out = tmp_path / "out"
    out.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
    env["OUT"] = str(out).replace("\\", "/")
    env.pop("DECKBENCH_EXPLAIN", None)
    env.pop("STS2SIM_USER_MODS", None)
    if os.name == "nt":
        # Git Bash would rewrite arguments that contain a slash.
        env["MSYS_NO_PATHCONV"] = "1"
        env["MSYS2_ARG_CONV_EXCL"] = "*"
    script = "set -e\n" + "\n".join(runnable)
    proc = subprocess.run([bash, "-c", script], cwd=ROOT, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, (proc.stdout[-2000:] + "\n" + proc.stderr[-4000:])
    text = proc.stdout
    for phrase in (
        "Wilson 95% CI",
        "two-proportion z-test",
        "p=1.0000",
        "样本不足，不能下结论",
        "sample too small to conclude",
        "n=2 < 30",
        "n=2 and n=2 < 30",
        "workers 2",
        "mechanic_aware True",
        "Arc",
        "←",
    ):
        assert phrase in text, phrase

    win_rows = _jsonl(out / "win" / "raw.jsonl")
    ab_rows = _jsonl(out / "ab" / "raw.jsonl")
    assert len(win_rows) == 2 and len(ab_rows) == 4
    assert {r["result"] for r in win_rows + ab_rows} == {"timeout"}
    assert {r["deck"] for r in ab_rows} == {"spark_base", "spark_arc"}
    win_meta = json.loads((out / "win" / "meta.json").read_text(encoding="utf-8"))
    mech_meta = json.loads((out / "mechanic" / "meta.json").read_text(encoding="utf-8"))
    assert win_meta["jobs"] == 2
    assert mech_meta["exp"]["agent_kw"]["mechanic_aware"] is True
    assert "explain" not in win_meta
    report = (out / "win" / "report.md").read_text(encoding="utf-8")
    assert "No local monster codex, so this section was skipped." in report
    explain = (out / "explain" / "explain.jsonl").read_text(encoding="utf-8")
    assert "ARC" in explain or "Arc" in explain


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
