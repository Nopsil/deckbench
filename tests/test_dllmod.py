"""真实 mod DLL → YAML 的导入。夹具是本仓库自己的合成程序集，不需要游戏。"""
import base64
import json
import os
import zipfile

import pytest

from sts2sim.dllmod.extract import parse_sources
from sts2sim.dllmod.metadata import AssemblyInfo, read_assembly
from sts2sim.dllmod.package import DllModError, _to_mod, import_installed, import_path, list_installed
from sts2sim.modfmt import schema as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "dllmod")
EXTRA = os.path.join(FIX, "extra")


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


def test_import_dll_route_returns_editor_mod(tmp_path):
    pytest.importorskip("fastapi")
    httpx = pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from gui.server import app
    zpath = tmp_path / "one.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("SyntheticMod/SyntheticMod.dll", _dll_bytes())
        z.writestr("SyntheticMod/SyntheticMod.json", json.dumps({
            "id": "SyntheticMod", "name": "Synthetic Mod", "has_dll": True, "dependencies": []}))
    with TestClient(app) as client:
        up = client.post("/api/modeditor/import-dll", files={"file": ("one.zip", zpath.read_bytes(), "application/zip")},
                         headers={"x-lang": "en"})
        assert up.status_code == 200, up.text
        body = up.json()
        assert body["_dll"]["name"] == "Synthetic Mod"
        assert body["_dll"]["cards"] >= 3
        assert any("not executed" in w["en"].lower() for w in body["_check"]["warnings"])
        bad = client.post("/api/modeditor/import-dll", files={"file": ("x.zip", b"not a zip", "application/zip")},
                          headers={"x-lang": "en"})
        assert bad.status_code == 400 and "zip" in bad.json()["detail"].lower()
        listed = client.get("/api/modeditor/installed")
        assert listed.status_code == 200 and isinstance(listed.json(), list)
    del httpx


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


ILSPY = os.path.join(FIX, "ilspy")
_SPEC_FIELDS = (
    "status", "kind", "cost", "type", "rarity", "target", "keywords", "tags", "vars",
    "upgrade_vars", "upgrade_cost", "effects", "triggers", "stack", "power_type", "show",
)


def test_authored_source_matches_ilspy_fixture():
    assert _specs(FIX) == _specs(ILSPY)
    specs, regs, ordinal = _specs(FIX)
    assert ordinal is False
    assert [cls for _pool, cls in regs] == ["NotebookStrike", "FieldKit", "UnreadNote"]
    assert set(specs) == {"NotebookStrike", "FieldKit", "UnreadNote", "SteadyPower", "PocketRuler"}
    strike = specs["NotebookStrike"]
    assert strike["status"] == "translated"
    assert "hits" not in strike["effects"][0]
    assert strike["effects"] == [{"op": "damage", "amount": "Damage"}]
    assert strike["upgrade_vars"] == {"Damage": 9}
    kit = specs["FieldKit"]
    assert kit["keywords"] == ["Exhaust"] and kit["upgrade_vars"] == {"Block": 9}
    assert "Cards" not in kit["upgrade_vars"]
    assert specs["UnreadNote"]["status"] == "partial" and specs["UnreadNote"]["effects"] == []
    assert specs["SteadyPower"]["triggers"] == [{"on": "turn_start", "do": [{"op": "block", "amount": "Block"}]}]
    assert specs["PocketRuler"]["rarity"] == "Starter"
    assert specs["PocketRuler"]["triggers"][0]["do"] == [{"op": "block", "amount": 4}]
    for name, spec in specs.items():
        assert set(_SPEC_FIELDS) <= set(spec)


@pytest.mark.parametrize("fn", [
    "NotebookStrike.cs", "FieldKit.cs", "UnreadNote.cs", "SteadyPower.cs", "PocketRuler.cs", "ModEntry.cs",
])
def test_each_ilspy_fixture_file_parses_alone(fn):
    specs, regs, ordinal = parse_sources({fn: _text(os.path.join(ILSPY, fn))})
    assert ordinal is False
    if fn == "ModEntry.cs":
        assert specs == {}
        assert regs == [
            ("NotebookCardPool", "NotebookStrike"),
            ("NotebookCardPool", "FieldKit"),
            ("NotebookCardPool", "UnreadNote"),
        ]
        return
    cls = fn[:-3]
    assert list(specs) == [cls] and regs == []
    spec = specs[cls]
    if cls == "UnreadNote":
        assert spec["status"] == "partial" and spec["effects"] == []
        assert (spec["type"], spec["rarity"], spec["cost"], spec["target"]) == ("Skill", "Rare", 0, "Self")
    else:
        assert spec["status"] == "translated"
        assert spec["effects"] or spec["triggers"]


def _yaml(sources, refs=("sts2",), deps=()):
    specs, regs, ordinal = parse_sources(sources)
    info = AssemblyInfo("SyntheticMod", list(refs), [
        {"name": n, "namespace": "SyntheticMod", "base": "CardModel", "kind": specs[n]["kind"], "abstract": False}
        for n in specs
    ], [])
    mod, report = _to_mod({"id": "SyntheticMod", "name": "Synthetic Mod", "dependencies": list(deps)},
                          info, specs, regs, ordinal, {}, True, None)
    return specs, mod, report


def test_fixture_yaml_leaves_the_branch_blank():
    files = {fn: _text(os.path.join(ILSPY, fn)) for fn in os.listdir(ILSPY) if fn.endswith(".cs")}
    _specs_map, mod, report = _yaml(files)
    assert report["mode"] == "decompiled"
    assert report["pools"] == [
        {"pool": "NotebookCardPool", "class": "NotebookStrike", "vanilla": None},
        {"pool": "NotebookCardPool", "class": "FieldKit", "vanilla": None},
        {"pool": "NotebookCardPool", "class": "UnreadNote", "vanilla": None},
    ]
    assert any("not executed" in x["en"].lower() for x in report["limitations"])
    assert not any("guessed" in x["en"].lower() for x in report["limitations"])
    by_id = {c["id"]: c for c in mod["cards"]}
    strike = by_id["NOTEBOOK_STRIKE"]
    assert strike["pool"] is False and strike["type"] == "Attack" and strike["target"] == "AnyEnemy"
    assert strike["effects"] == [{"op": "damage", "amount": "Damage"}]
    assert "hits" not in strike["effects"][0]
    assert strike["upgrade"]["vars"] == {"Damage": 9}
    kit = by_id["FIELD_KIT"]
    assert kit["pool"] is True and "Exhaust" in kit["keywords"]
    assert kit["effects"] == [{"op": "block", "amount": "Block"}, {"op": "draw", "n": "Cards"}]
    assert kit["upgrade"]["vars"] == {"Block": 9}
    note = by_id["UNREAD_NOTE"]
    assert note["effects"] == [] and note["type"] == "Skill" and note["rarity"] == "Rare" and note["cost"] == 0
    noted = next(n for n in report["notes"] if n["where"] == "UNREAD_NOTE")
    assert "left blank" in noted["en"] and "always happens" in noted["en"]
    power = next(p for p in mod["powers"] if p["id"] == "STEADY_POWER")
    assert power["type"] == "Buff" and power["stack"] == "Counter"
    assert power["triggers"][0]["on"] == "turn_start" and power["vars"]["Block"] == 2
    relic = next(r for r in mod["relics"] if r["id"] == "POCKET_RULER")
    assert relic["pool"] is False and relic["rarity"] == "Starter"
    assert relic["triggers"][0]["do"] == [{"op": "block", "amount": 4}]
    problems, _warnings = S.validate(mod, fullrun=False)
    assert not problems


_STRAIGHT = r'''
public class Mix : CardModel {
    protected override IEnumerable<DynamicVar> CanonicalVars => new[] {
        new DamageVar(6m, 0), new EnergyVar(1), new DynamicVar("Power", 3m)
    };
    public Mix() : base(1, CardType.Attack, CardRarity.Common, TargetType.AllEnemies) {}
    protected override HashSet<CardKeyword> CanonicalKeywords => new HashSet<CardKeyword> {
        CardKeyword.Ethereal, CardKeyword.Retain, CardKeyword.NotARealOne
    };
    protected override HashSet<CardTag> CanonicalTags => new HashSet<CardTag> { CardTag.Strike, CardTag.Other };
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await DamageCmd.Attack(DynamicVars.Damage.BaseValue).WithHitCount(3).Execute(c);
        await PlayerCmd.GainEnergy(DynamicVars.Energy.BaseValue);
        await PlayerCmd.LoseEnergy(1);
        await CardPileCmd.Draw(c, 2);
        await CreatureCmd.Heal(Owner.Creature, 5m);
        await PowerCmd.Apply<StrengthPower>(c, cardPlay.Target, DynamicVars["Power"].BaseValue, null, false);
    }
    protected override void OnUpgrade() {
        DynamicVars.Damage.UpgradeValueBy(2m);
        EnergyCost.UpgradeBy(-1);
    }
}
public class Hidden : CardModel {
    public Hidden() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self, false) {}
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await CreatureCmd.GainBlock(Owner, 3m, null);
    }
}
public class Rand : CardModel {
    public Rand() : base(1, CardType.Attack, CardRarity.Common, TargetType.RandomEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await DamageCmd.Attack(4m).TargetingAll().Execute(c);
    }
}
public class EndPow : PowerModel {
    public override async Task AfterTurnEnd(PlayerChoiceContext c, CombatSide side) {
        await CreatureCmd.GainBlock(Owner, 2m, null);
    }
}
'''


def test_synthetic_straight_line_effects_become_yaml():
    _specs_map, mod, report = _yaml({"mix.cs": _STRAIGHT})
    mix = next(c for c in mod["cards"] if c["id"] == "MIX")
    assert mix["keywords"] == ["Ethereal", "Retain"]
    assert mix["tags"] == ["Strike"]
    assert mix["target"] == "AllEnemies" and mix["pool"] is True
    assert mix["vars"] == {"Damage": 6, "Energy": 1, "Power": 3}
    assert mix["effects"] == [
        {"op": "damage", "amount": "Damage", "hits": 3, "target": "all"},
        {"op": "energy", "n": "Energy"},
        {"op": "energy", "n": -1},
        {"op": "draw", "n": 2},
        {"op": "heal", "amount": 5},
        {"op": "apply", "power": "STRENGTH", "amount": "Power", "target": "target"},
    ]
    assert mix["upgrade"]["vars"] == {"Damage": 8} and mix["upgrade"]["cost"] == 0
    hidden = next(c for c in mod["cards"] if c["id"] == "HIDDEN")
    assert hidden["pool"] is False and hidden["effects"] == [{"op": "block", "amount": 3}]
    rand = next(c for c in mod["cards"] if c["id"] == "RAND")
    assert rand["target"] == "RandomEnemy"
    assert rand["effects"] == [{"op": "damage", "amount": 4, "target": "all"}]
    power = next(p for p in mod["powers"] if p["id"] == "END_POW")
    assert power["triggers"] == [{"on": "turn_end", "do": [{"op": "block", "amount": 2}]}]
    problems, _warnings = S.validate(mod, fullrun=False)
    assert not problems
    assert report["mode"] == "decompiled"


_PARTIAL = r'''
public class Branched : CardModel {
    public Branched() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self) {}
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await DamageCmd.Attack(6m).Execute(c);
        if (Owner != null) { await CreatureCmd.GainBlock(Owner, 4m, null); }
    }
}
public class Bare : CardModel {
    public Bare() : base(2, CardType.Power, CardRarity.Uncommon, TargetType.Self) {}
}
public class BadUp : CardModel {
    protected override IEnumerable<DynamicVar> CanonicalVars => new[] { new DamageVar(6m, 0) };
    public BadUp() : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await DamageCmd.Attack(DynamicVars.Damage.BaseValue).Execute(c);
    }
    protected override void OnUpgrade() {
        DynamicVars.Missing.UpgradeValueBy(1m);
    }
}
public class NumKw : CardModel {
    public NumKw() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self) {}
    protected override HashSet<CardKeyword> CanonicalKeywords => new HashSet<CardKeyword> { (CardKeyword)3, CardKeyword.Exhaust };
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await CreatureCmd.GainBlock(Owner, 4m, null);
    }
}
'''


def test_partial_cards_do_not_guess_branches_or_keyword_numbers():
    specs, _regs, ordinal = parse_sources({"partial.cs": _PARTIAL})
    assert ordinal is True
    assert specs["Branched"]["status"] == "partial" and specs["Branched"]["effects"] == []
    assert specs["Bare"]["status"] == "partial" and specs["Bare"]["effects"] == []
    assert specs["BadUp"]["status"] == "partial"
    assert specs["BadUp"]["effects"] == [{"op": "damage", "amount": "Damage"}]
    assert specs["BadUp"]["upgrade_vars"] == {} and specs["BadUp"]["upgrade_cost"] is None
    assert specs["NumKw"]["keywords"] == ["Exhaust"]
    _specs_map, mod, report = _yaml({"partial.cs": _PARTIAL})
    notes = {n["where"]: n["en"] for n in report["notes"]}
    assert "always happens" in notes["BRANCHED"] and "left blank" in notes["BRANCHED"]
    assert next(c for c in mod["cards"] if c["id"] == "BRANCHED")["effects"] == []
    assert "recognized are kept" in notes["BAD_UP"]
    assert next(c for c in mod["cards"] if c["id"] == "BAD_UP")["effects"] == [{"op": "damage", "amount": "Damage"}]
    assert next(c for c in mod["cards"] if c["id"] == "NUM_KW")["keywords"] == ["Exhaust"]
    assert any("not guessed" in x["en"] for x in report["limitations"])


_CAST = r'''
public class NotebookStrike : CardModel {
    public NotebookStrike() : base(1, CardType.Attack, CardRarity.Basic, TargetType.AnyEnemy) {}
    protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
        await DamageCmd.Attack(6m).Execute(c);
    }
}
public class Tonic : PotionModel {
    public Tonic() : base(0, CardType.Skill, CardRarity.Common, TargetType.Self) {}
    protected override async Task OnUse(PlayerChoiceContext c) {
        await CreatureCmd.Heal(Owner.Creature, 7m);
    }
}
public class PocketRuler : RelicModel {
    public override RelicRarity Rarity => RelicRarity.Starter;
    public override async Task BeforeCombat(PlayerChoiceContext c) {
        await CreatureCmd.GainBlock(Owner.Creature, 4m, null);
    }
}
public class NotebookHero : CharacterModel {
    public override int StartingHp => 72;
    public override int MaxEnergy => 3;
    public override int StartingGold { get { return 99; } }
    public override IEnumerable<CardModel> StartingDeck => new NotebookStrike[] { new NotebookStrike(), new NotebookStrike() };
}
public static class ModEntry {
    public static void Initialize() {
        ModHelper.AddModelToPool<IroncladCardPool, NotebookStrike>();
        ModHelper.AddModelToPool<NotebookCardPool, Tonic>();
    }
}
'''


def test_potion_character_and_vanilla_pool_yaml():
    specs, mod, report = _yaml({"cast.cs": _CAST})
    assert specs["NotebookHero"]["starting_deck"] == ["NotebookStrike", "NotebookStrike"]
    assert specs["NotebookHero"]["hp"] == 72 and specs["NotebookHero"]["energy"] == 3
    assert specs["Tonic"]["effects"] == [{"op": "heal", "amount": 7}]
    hero = mod["meta"]["characters"]["NOTEBOOK_HERO"]
    assert hero["hp"] == 72 and hero["energy"] == 3 and hero["gold"] == 99
    assert hero["starting_deck"] == ["NOTEBOOK_STRIKE×2"]
    assert hero["relics"] == ["POCKET_RULER"] and hero["class"] == "NotebookHero"
    tonic = next(p for p in mod["potions"] if p["id"] == "TONIC")
    assert tonic["effects"] == [{"op": "heal", "amount": 7}] and tonic["target"] == "Self"
    assert report["pools"] == [
        {"pool": "IroncladCardPool", "class": "NotebookStrike", "vanilla": "Ironclad"},
        {"pool": "NotebookCardPool", "class": "Tonic", "vanilla": None},
    ]
    problems, _warnings = S.validate(mod, fullrun=False)
    assert not problems


def test_metadata_import_does_not_decompile(tmp_path, monkeypatch):
    folder = tmp_path / "SyntheticMod"
    folder.mkdir()
    (folder / "SyntheticMod.dll").write_bytes(_dll_bytes())
    (folder / "SyntheticMod.json").write_text(json.dumps({
        "id": "SyntheticMod", "name": "Synthetic Mod", "has_dll": True, "dependencies": []}), encoding="utf-8")

    def boom(*_a, **_k):
        raise AssertionError("decompile should not run")

    monkeypatch.setattr("sts2sim.dllmod.package._decompile", boom)
    mod, report = import_path(str(folder), decompile=False)
    assert report["mode"] == "metadata"
    assert report["cards"] and all(c["status"] == "inventory" for c in report["cards"])
    assert all(c["type"] is None for c in mod["cards"])
    problems, _warnings = S.validate(mod, fullrun=False)
    assert problems


@pytest.mark.parametrize("name", ["sts2.dll", "GodotSharp.dll", "0Harmony.dll"])
def test_game_assemblies_are_rejected_by_name(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"not the game")
    with pytest.raises(DllModError) as err:
        import_path(str(path), decompile=False)
    assert err.value.key == "err.dllGame"


def test_unreadable_and_ambiguous_packages_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("sts2sim.gamedata.find_dll", lambda game_dir=None: None)
    assert list_installed() == []
    with pytest.raises(DllModError) as missing:
        import_installed("Anything")
    assert missing.value.key == "err.dllNone"
    with pytest.raises(DllModError) as bad_id:
        import_installed("../sts2")
    assert bad_id.value.key == "err.dllNone"
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(DllModError) as none:
        import_path(str(empty), decompile=False)
    assert none.value.key == "err.dllNone"
    folder = tmp_path / "Broken"
    folder.mkdir()
    (folder / "Broken.dll").write_bytes(b"MZ" + b"\x00" * 80)
    (folder / "Broken.json").write_text(json.dumps({
        "id": "Broken", "name": "Broken", "has_dll": True, "dependencies": []}), encoding="utf-8")
    with pytest.raises(DllModError) as read:
        import_path(str(folder), decompile=False)
    assert read.value.key == "err.dllRead"
    zpath = tmp_path / "two.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("m/A.dll", _dll_bytes())
        z.writestr("m/B.dll", _dll_bytes())
    with pytest.raises(DllModError) as many:
        import_path(str(zpath), decompile=False)
    assert many.value.key == "err.dllMany"


def test_decompile_real_fixture_when_ilspy_exists(tmp_path, monkeypatch):
    from sts2sim import gamedata
    if gamedata._find_ilspy()[0] is None:
        pytest.skip("ilspycmd not installed")
    # 夹具按桩的枚举序数编译。反编译时把 find_dll 固定成找不到游戏（并清掉 DECKBENCH_GAME_DIR），
    # 有安装的机器和 CI 都只拿到数字枚举，不会把真 sts2.dll 加进引用。
    monkeypatch.delenv("DECKBENCH_GAME_DIR", raising=False)
    monkeypatch.setattr(gamedata, "find_dll", lambda game_dir=None: None)
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
        by_id = {n["where"]: n["en"] for n in report["notes"]}
        assert "are kept" in by_id["FIELD_KIT"]
        assert "left blank" in by_id["UNREAD_NOTE"]


def test_extra_source_and_ilspy_cover_supported_ops():
    for folder in (EXTRA, os.path.join(EXTRA, "ilspy")):
        specs, _regs, ordinal = _specs(folder)
        assert not ordinal
        wind = specs["SecondWind"]
        assert wind["status"] == "translated"
        assert wind["vars"] == {"Energy": 1, "Heal": 4}
        assert wind["effects"] == [{"op": "energy", "n": "Energy"}, {"op": "heal", "amount": "Heal"}]
        tap = specs["TripleTap"]
        assert tap["effects"] == [{"op": "damage", "amount": "Damage", "hits": 3}]
        sweep = specs["WideSweep"]
        assert sweep["target"] == "AllEnemies"
        assert sweep["effects"] == [{"op": "damage", "amount": "Damage", "target": "all"}]
        coin = specs["CoinToss"]
        assert coin["effects"] == [{"op": "damage", "amount": "Damage", "target": "random"}]
        cheap = specs["CheapInk"]
        assert cheap["upgrade_cost"] == 0 and cheap["effects"] == [{"op": "block", "amount": 5}]
        tax = specs["TaxingThought"]
        assert tax["effects"] == [{"op": "energy", "n": -1}]
        sticky = specs["StickyMemo"]
        assert sticky["keywords"] == ["Ethereal", "Retain"] and sticky["tags"] == ["Strike"]
        flex = specs["FlexPencil"]
        assert flex["effects"] == [{"op": "apply", "power_class": "StrengthPower", "amount": 2}]
        hidden = specs["HiddenNote"]
        assert hidden["show"] is False and hidden["effects"] == [{"op": "damage", "amount": 4}]
        guard = specs["NullGuard"]
        assert guard["status"] == "translated" and guard["effects"] == [{"op": "block", "amount": 4}]
        late = specs["LateFee"]
        assert late["triggers"] == [{"on": "turn_end", "do": [{"op": "block", "amount": 2}]}]
        shop = specs["ShopBookmark"]
        assert shop["rarity"] == "Shop"
        assert shop["triggers"] == [{"on": "turn_end", "do": [{"op": "energy", "n": 1}]}]
        salve = specs["SalveVial"]
        assert salve["status"] == "translated" and salve["effects"] == [{"op": "heal", "amount": 6}]
        scribe = specs["Scribe"]
        assert (scribe["hp"], scribe["energy"], scribe["gold"]) == (70, 3, 99)
        assert scribe["starting_deck"] == ["TripleTap", "TripleTap", "SecondWind", "StickyMemo"]


def test_extra_round_trips_through_yaml():
    specs, _regs, ordinal = _specs(EXTRA)
    from sts2sim.dllmod.metadata import AssemblyInfo
    from sts2sim.dllmod.package import _to_mod
    info = AssemblyInfo("SyntheticMod", ["sts2"], [
        {"name": n, "namespace": "SyntheticMod", "base": "", "kind": specs[n]["kind"], "abstract": False}
        for n in specs
    ], [])
    mod, report = _to_mod({"id": "SyntheticMod", "name": "Synthetic Mod", "dependencies": []},
                          info, specs, [], ordinal, {}, True, None)
    assert report["mode"] == "decompiled"
    again = S.load_mod_files(S.dump_mod_dir(mod))
    problems, _w = S.validate(again, fullrun=False)
    assert not problems
    wind = next(c for c in again["cards"] if c["id"] == "SECOND_WIND")
    assert [e["op"] for e in wind["effects"]] == ["energy", "heal"]
    coin = next(c for c in again["cards"] if c["id"] == "COIN_TOSS")
    assert coin["effects"][0]["target"] == "random"
    flex = next(c for c in again["cards"] if c["id"] == "FLEX_PENCIL")
    assert flex["effects"][0]["power"] == "STRENGTH" and "power_class" not in flex["effects"][0]
    hidden = next(c for c in again["cards"] if c["id"] == "HIDDEN_NOTE")
    assert hidden["pool"] is False
    cheap = next(c for c in again["cards"] if c["id"] == "CHEAP_INK")
    assert cheap["upgrade"]["cost"] == 0
    salve = next(p for p in again["potions"] if p["id"] == "SALVE_VIAL")
    assert salve["effects"] == [{"op": "heal", "amount": 6}]
    late = next(p for p in again["powers"] if p["id"] == "LATE_FEE")
    assert late["triggers"][0]["on"] == "turn_end"
    shop = next(r for r in again["relics"] if r["id"] == "SHOP_BOOKMARK")
    assert shop["rarity"] == "Shop"
    scribe = again["characters"]["SCRIBE"]
    assert scribe["hp"] == 70 and "TRIPLE_TAP×2" in scribe["starting_deck"]
    assert "STICKY_MEMO" in scribe["starting_deck"]


def test_random_targeting_is_not_imported_as_single_target():
    src = """
    public sealed class Coin : CardModel {
        public Coin() : base(1, CardType.Attack, CardRarity.Common, TargetType.AnyEnemy) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            await DamageCmd.Attack(9m).TargetingRandomOpponents(c.CombatState).Execute(c);
        }
    }
    """
    specs, _regs, ordinal = parse_sources({"a.cs": src})
    assert not ordinal
    assert specs["Coin"]["effects"] == [{"op": "damage", "amount": 9, "target": "random"}]


def test_null_coalescing_throw_is_not_a_branch():
    src = """
    public sealed class Guard : CardModel {
        public Guard() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            await CreatureCmd.GainBlock(Owner.Creature ?? throw new InvalidOperationException(), 4m, p);
        }
    }
    """
    specs, _regs, _ordinal = parse_sources({"a.cs": src})
    assert specs["Guard"]["status"] == "translated"
    assert specs["Guard"]["effects"] == [{"op": "block", "amount": 4}]


def test_null_coalesce_to_another_value_stays_blank():
    src = """
    public sealed class Maybe : CardModel {
        public Maybe() : base(1, CardType.Skill, CardRarity.Common, TargetType.Self) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            await CreatureCmd.GainBlock(Owner.Creature ?? other, 4m, p);
        }
    }
    """
    specs, _regs, _ordinal = parse_sources({"a.cs": src})
    assert specs["Maybe"]["status"] == "partial" and specs["Maybe"]["effects"] == []


def test_starting_deck_reads_card_from_generic():
    src = """
    public sealed class Hero : CharacterModel {
        public override IEnumerable<CardModel> StartingDeck => new[] {
            new TripleTap(), Card.From<NotebookStrike>(), new Card<FieldKit>()
        };
    }
    """
    specs, _regs, _ordinal = parse_sources({"a.cs": src})
    assert specs["Hero"]["starting_deck"] == ["TripleTap", "NotebookStrike", "FieldKit"]


def test_potion_without_card_ctor_translates_heal():
    src = """
    public sealed class Salve : PotionModel {
        protected override async Task OnUse(PlayerChoiceContext c) {
            await CreatureCmd.Heal(Owner.Creature, 6m);
        }
    }
    """
    specs, _regs, _ordinal = parse_sources({"a.cs": src})
    assert specs["Salve"]["status"] == "translated"
    assert specs["Salve"]["effects"] == [{"op": "heal", "amount": 6}]


def test_foreach_and_unknown_commands_still_blank_the_method():
    src = """
    public sealed class Loop : CardModel {
        public Loop() : base(1, CardType.Skill, CardRarity.Rare, TargetType.Self) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            foreach (var e in c.CombatState.Enemies)
                await CreatureCmd.GainBlock(Owner.Creature, 1m, p);
        }
    }
    public sealed class Custom : CardModel {
        public Custom() : base(1, CardType.Skill, CardRarity.Rare, TargetType.Self) {}
        protected override async Task OnPlay(PlayerChoiceContext c, CardPlay p) {
            await CreatureCmd.GainBlock(Owner.Creature, 4m, p);
            await MysteryCmd.DoThing(c);
        }
    }
    """
    specs, _regs, _ordinal = parse_sources({"a.cs": src})
    assert specs["Loop"]["status"] == "partial" and specs["Loop"]["effects"] == []
    assert specs["Custom"]["status"] == "partial" and specs["Custom"]["effects"] == []


def test_decompile_true_without_ilspy_stays_metadata(tmp_path, monkeypatch):
    from sts2sim import gamedata
    monkeypatch.setattr(gamedata, "_find_ilspy", lambda: (None, None))
    folder = tmp_path / "SyntheticMod"
    folder.mkdir()
    (folder / "SyntheticMod.dll").write_bytes(_dll_bytes())
    (folder / "SyntheticMod.json").write_text(json.dumps({
        "id": "SyntheticMod", "name": "Synthetic Mod", "has_dll": True, "dependencies": []}), encoding="utf-8")
    mod, report = import_path(str(folder), decompile=True)
    assert report["mode"] == "metadata"
    assert report["decompile_error"]
    ids = {c["id"] for c in mod["cards"]}
    assert "NOTEBOOK_STRIKE" in ids
    problems, _w = S.validate(mod, fullrun=False)
    assert problems


def test_list_installed_is_empty_without_a_game():
    from sts2sim.dllmod.package import list_installed
    assert list_installed(game_dir=str(os.path.join(FIX, "no-such-install"))) == []
