"""真实 mod DLL → YAML 的导入。夹具是本仓库自己的合成程序集，不需要游戏。"""
import base64
import json
import os
import zipfile

import pytest

from sts2sim.dllmod.extract import parse_sources
from sts2sim.dllmod.metadata import read_assembly
from sts2sim.dllmod.package import DllModError, import_path
from sts2sim.modfmt import schema as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "dllmod")


def _text(path):
    return open(path, encoding="utf-8").read()


def _specs(folder):
    files = {}
    for fn in os.listdir(folder):
        if fn.endswith(".cs"):
            files[fn] = _text(os.path.join(folder, fn))
    return parse_sources(files)


def test_source_and_ilspy_extract_the_same_straight_line_cards():
    for folder in (FIX, os.path.join(FIX, "ilspy")):
        specs, regs, ordinal = _specs(folder)
        assert not ordinal
        strike = specs["NotebookStrike"]
        assert strike["status"] == "translated"
        assert (strike["type"], strike["rarity"], strike["cost"], strike["target"]) == ("Attack", "Basic", 1, "AnyEnemy")
        assert strike["vars"] == {"Damage": 6}
        assert strike["upgrade_vars"] == {"Damage": 9}
        assert strike["effects"] == [{"op": "damage", "amount": "Damage"}]
        kit = specs["FieldKit"]
        assert kit["status"] == "translated"
        assert kit["keywords"] == ["Exhaust"]
        assert kit["vars"] == {"Block": 6, "Cards": 1}
        assert kit["upgrade_vars"] == {"Block": 9}
        assert kit["effects"] == [{"op": "block", "amount": "Block"}, {"op": "draw", "n": "Cards"}]
        note = specs["UnreadNote"]
        assert note["status"] == "partial" and note["effects"] == []
        assert note["type"] == "Skill" and note["rarity"] == "Rare"
        power = specs["SteadyPower"]
        assert power["status"] == "translated"
        assert power["triggers"] == [{"on": "turn_start", "do": [{"op": "block", "amount": "Block"}]}]
        relic = specs["PocketRuler"]
        assert relic["rarity"] == "Starter"
        assert relic["triggers"][0]["on"] == "battle_start"
        assert relic["triggers"][0]["do"] == [{"op": "block", "amount": 4}]
        assert ("NotebookCardPool", "FieldKit") in regs


def test_ordinal_enums_are_not_guessed():
    src = """
    public sealed class NumCard : CardModel {
        public NumCard() : base(1, (CardType)0, (CardRarity)0, (TargetType)0) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            await DamageCmd.Attack(DynamicVars.Damage.BaseValue).Execute(c);
        }
        protected override IEnumerable<DynamicVar> CanonicalVars => new DamageVar(6m, 0);
    }
    """
    specs, _regs, ordinal = parse_sources({"a.cs": src})
    card = specs["NumCard"]
    assert ordinal and card["type"] is None and card["rarity"] is None and card["target"] is None
    assert card["effects"] == [{"op": "damage", "amount": "Damage"}]
    assert card["status"] == "partial"


def _dll_bytes():
    return base64.b64decode(_text(os.path.join(FIX, "SyntheticMod.dll.b64")))


def test_metadata_lists_models_without_executing(tmp_path):
    dll = tmp_path / "SyntheticMod.dll"
    dll.write_bytes(_dll_bytes())
    info = read_assembly(str(dll))
    assert info.name == "SyntheticMod"
    assert "sts2" in info.refs
    kinds = {t["name"]: t["kind"] for t in info.models()}
    assert kinds["NotebookStrike"] == "card"
    assert kinds["SteadyPower"] == "power"
    assert kinds["PocketRuler"] == "relic"
    assert info.initializers == [("ModEntry", "Initialize")]
    folder = tmp_path / "SyntheticMod"
    folder.mkdir()
    (folder / "SyntheticMod.dll").write_bytes(dll.read_bytes())
    (folder / "SyntheticMod.json").write_text(json.dumps({
        "id": "SyntheticMod", "name": "Synthetic Mod", "author": "DeckBench tests",
        "version": "0.0.1", "has_dll": True, "has_pck": False, "dependencies": [],
        "affects_gameplay": True}), encoding="utf-8")
    (folder / "localization" / "eng").mkdir(parents=True)
    (folder / "localization" / "eng" / "cards.json").write_text(
        json.dumps({"NOTEBOOK_STRIKE.title": "Notebook Strike", "NOTEBOOK_STRIKE.description": "Deal {Damage}."}),
        encoding="utf-8")
    mod, report = import_path(str(folder), decompile=False)
    assert report["mode"] == "metadata"
    assert report["initializer"] == "Initialize"
    ids = {c["id"] for c in mod["cards"]}
    assert "NOTEBOOK_STRIKE" in ids
    strike = next(c for c in mod["cards"] if c["id"] == "NOTEBOOK_STRIKE")
    assert strike["name"] == "Notebook Strike"
    assert strike["type"] is None  # 占位的 UNKNOWN 过不了格式表，避免拿假费用去跑
    assert any("not executed" in x["en"].lower() or "not executed" in x["en"] for x in report["limitations"])
    problems, _warnings = S.validate(mod, fullrun=False)
    assert problems  # 元数据模式不能当成已经能打的牌


def test_ilspy_text_round_trips_through_yaml():
    files = {fn: _text(os.path.join(FIX, "ilspy", fn)) for fn in os.listdir(os.path.join(FIX, "ilspy"))}
    specs, regs, ordinal = parse_sources(files)
    assert specs["FieldKit"]["status"] == "translated" and not ordinal
    # 走和 CLI 一样的组装：用元数据 + 这些源码。这里直接用 import 需要 DLL，YAML 形状用 schema 再读一遍。
    from sts2sim.dllmod.package import _to_mod
    from sts2sim.dllmod.metadata import AssemblyInfo
    info = AssemblyInfo("SyntheticMod", ["sts2"], [
        {"name": n, "namespace": "SyntheticMod", "base": "CardModel", "kind": specs[n]["kind"], "abstract": False}
        for n in specs
    ], [("ModEntry", "Initialize")])
    manifest = {"id": "SyntheticMod", "name": "Synthetic Mod", "dependencies": []}
    mod, report = _to_mod(manifest, info, specs, regs, ordinal, {}, True, None)
    assert report["mode"] == "decompiled"
    again = S.load_mod_files(S.dump_mod_dir(mod))
    strike = next(c for c in again["cards"] if c["id"] == "NOTEBOOK_STRIKE")
    assert strike["type"] == "Attack" and strike["class"] == "NotebookStrike"
    assert strike["effects"][0]["op"] == "damage"
    kit = next(c for c in again["cards"] if c["id"] == "FIELD_KIT")
    assert "Exhaust" in kit["keywords"] and kit["pool"] is not False
    assert next(c for c in again["cards"] if c["id"] == "NOTEBOOK_STRIKE")["pool"] is False
    problems, _w = S.validate(again, fullrun=False)
    assert not problems
    power = next(p for p in again["powers"] if p["id"] == "STEADY_POWER")
    assert power["triggers"][0]["on"] == "turn_start"
    relic = next(r for r in again["relics"] if r["id"] == "POCKET_RULER")
    assert relic["pool"] is False and relic["rarity"] == "Starter"


def test_apply_power_links_to_the_mod_power_and_flags_harmony():
    src = """
    public class SteadyPower : PowerModel { }
    public class NoteCard : CardModel {
        public NoteCard() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self) {}
        protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay) {
            await PowerCmd.Apply<SteadyPower>(choiceContext, base.Owner, 2m, null, false);
        }
    }
    """
    specs, _regs, ordinal = parse_sources({"Note.cs": src})
    assert not ordinal
    assert specs["NoteCard"]["effects"] == [{"op": "apply", "power_class": "SteadyPower", "amount": 2}]
    from sts2sim.dllmod.metadata import AssemblyInfo
    from sts2sim.dllmod.package import _to_mod
    info = AssemblyInfo("SyntheticMod", ["sts2", "0Harmony"], [
        {"name": n, "kind": specs[n]["kind"], "abstract": False} for n in specs
    ], [])
    mod, report = _to_mod({"id": "SyntheticMod", "name": "Synthetic Mod", "dependencies": ["BaseLib"]},
                          info, specs, [], False, {}, True, None)
    card = next(c for c in mod["cards"] if c["id"] == "NOTE_CARD")
    assert card["effects"][0]["power"] == "STEADY_POWER"
    assert "power_class" not in card["effects"][0]
    assert any("Harmony" in x["en"] for x in report["limitations"])
    assert any("BaseLib" in x["en"] for x in report["limitations"])


def test_rejects_the_game_assembly_and_ambiguous_zips(tmp_path):
    game = tmp_path / "sts2.dll"
    game.write_bytes(b"not really the game")
    with pytest.raises(DllModError) as ei:
        import_path(str(game))
    assert ei.value.key == "err.dllGame"
    zpath = tmp_path / "two.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("a/A.json", json.dumps({"id": "A", "has_dll": True}))
        z.writestr("b/B.json", json.dumps({"id": "B", "has_dll": True}))
    with pytest.raises(DllModError) as em:
        import_path(str(zpath))
    assert em.value.key == "err.dllMany"


def test_editor_payload_keeps_limits_off_the_saved_mod(tmp_path):
    pytest.importorskip("fastapi")
    folder = tmp_path / "SyntheticMod"
    folder.mkdir()
    (folder / "SyntheticMod.dll").write_bytes(_dll_bytes())
    (folder / "SyntheticMod.json").write_text(json.dumps({
        "id": "SyntheticMod", "name": "Synthetic Mod", "has_dll": True, "dependencies": []}), encoding="utf-8")
    mod, report = import_path(str(folder), decompile=False)
    from gui.modeditor import _from_dll
    view = _from_dll(mod, report)
    assert view["_dll"]["cards"] >= 3 and view["_dll"]["translated"] == 0
    assert view["_check"]["problems"] and view["_check"]["warnings"]
    assert "_dll_report" not in view and "_dll" in view


def test_decompile_real_fixture_when_ilspy_exists(tmp_path):
    from sts2sim import gamedata
    if gamedata._find_ilspy()[0] is None:
        pytest.skip("ilspycmd not installed")
    folder = tmp_path / "SyntheticMod"
    folder.mkdir()
    (folder / "SyntheticMod.dll").write_bytes(_dll_bytes())
    (folder / "SyntheticMod.json").write_text(json.dumps({
        "id": "SyntheticMod", "name": "Synthetic Mod", "has_dll": True, "dependencies": []}), encoding="utf-8")
    mod, report = import_path(str(folder), decompile=True)
    if report["mode"] != "decompiled":
        pytest.skip("ilspycmd could not decompile the fixture: " + str(report.get("decompile_error")))
    strike = next(c for c in mod["cards"] if c["id"] == "NOTEBOOK_STRIKE")
    assert any(e.get("op") == "damage" for e in strike["effects"])
    # 没有游戏引用时枚举是数字，不能被猜成 Attack
    if strike["type"] is None:
        assert any("number" in x["en"].lower() or "guess" in x["en"].lower() for x in report["limitations"])
