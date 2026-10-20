"""Claude娘 v3.5 单场对拍：新引擎（转译游戏 + mods/claude_v35） vs 旧引擎（YAML + mods/claude_v34，按 v3.5 规则开关）。

两类场景，每个场景在两个引擎里搭出同样的局面，执行同样的操作，比较结果：
  card ：手里放 1 张牌（+5 张打击），设定敌人数量/风控层数/玩家格挡，对 0 号敌人打出一次。
         比较：各敌人掉血/格挡/风控/虚弱/易伤，玩家格挡/能量/抽牌数/反击层数/新增能力数。
  hit  ：玩家带 反击 n 层（+分类器/修正案/免责声明），敌人带 f 层风控，用敌人的攻击打玩家 h 段。
         比较：敌人掉血/风控、玩家掉血。
新引擎：开一局 Claude，在第一场战斗的第一个决策点按场景 fork 子进程，在子进程里改局面并执行，结果经管道传回。
旧引擎：直接构造 Combat。旧引擎的 v3.5 规则开关：STS2SIM_FANJI=hit-3-1H，STS2SIM_FLQ=mult0，STS2SIM_GRANT=6。

用法：.venv/bin/python tools/parity_v35.py [--only CID,...] [--out reports/full_run/parity_v35.md]
"""
import os
import sys
import json
import random
import argparse

os.environ.setdefault("STS2SIM_FANJI", "hit-3-1H")
os.environ.setdefault("STS2SIM_FLQ", "mult0")
os.environ.setdefault("STS2SIM_GRANT", "6")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "mods"), os.path.join(ROOT, "tests")]

from claude_v35.cards_v35 import CARDS   # noqa: E402

ENEMY_HP = 200
INTENT = 10          # 两个引擎的敌人意图统一为 10 点攻击 ×1（新引擎改意图不方便，所以按新引擎实际意图同步给旧引擎）


# 组合场景：先打能力/前置牌，再打触发它的牌（覆盖 RLHF、审计日志、清退名单、清理指标、熟练度、每回合限一次 等）
SEQS = [
    ("RLHF", "NOTEBOOK"), ("RLHF", "CHAIN_REVIEW"), ("RLHF", "MULTI_TURN"), ("RLHF", "FK_SPREAD"),
    ("AUDIT_LOG", "NOTEBOOK", "STICKER"), ("AUDIT_LOG", "MULTI_TURN"),
    ("CLEAR_LIST", "VERIFIED"), ("CLEAR_LIST", "PERMA_BAN"), ("CLEAR_LIST", "MASS_BAN"), ("CLEAR_LIST", "ONE_CLICK_BAN"),
    ("CLEAR_LIST", "QUICK_REVIEW"), ("CLEAR_LIST", "CREDIT_DEDUCT"), ("CLEAR_LIST", "MAKE_EXAMPLE"),
    ("CLEANUP_METRIC", "VERIFIED"), ("CLEANUP_METRIC", "RED_BUTTON"), ("CLEANUP_METRIC", "MASS_BAN"),
    ("CLEANUP_METRIC", "INSTA_BAN"),
    ("PRACTICE", "VERIFIED", "DASH_COMBO"), ("PRACTICE", "MASS_BAN", "CLAUDE_STRIKE"),
    ("CREDIT_DEDUCT", "CREDIT_DEDUCT"), ("IMMEDIATE", "IMMEDIATE"), ("STICKER", "COMPLIANCE_FIX", "EVIDENCE"),
    ("CLASSIFIER", "CLASSIFIER", "AMENDMENT"), ("SITE_RECTIFY", "NETWORK_NOTICE"), ("RLHF", "AUDIT_LOG", "CLEAR_LIST", "QUICK_REVIEW"),
]


# 跨回合场景：打出后结束回合，比较下个玩家回合开始时的 抽牌/能量/反击/风控/力量（敌人用新引擎的真实意图）
TURNS = [("PLAN_MODE",), ("LET_ME_THINK",), ("RISK_ALERT",), ("STACK_FIRST",), ("OPUS_FORM",), ("GEN_ARTIFACT",),
         ("DISCLAIMER",), ("CANT_HELP",), ("DOUBLE_CHECK",), ("DOUBLE_CHECK", "RED_TEAM"), ("RLHF", "RISK_ALERT"),
         ("CLAUDE_DEFEND",)]
TURN_KEYS = ("hand", "en", "fanji", "fk", "str")


def scenarios(only=None):
    out = []
    for cid, c in CARDS.items():
        if only and cid not in only:
            continue
        for up in (False, True):
            for ne in (1, 2):
                for f in (0, 3, 6, 12):
                    out.append({"kind": "card", "cid": cid, "up": up, "ne": ne, "fk": [f, 4][:ne], "blk": 7})
    for seq in SEQS:
        if only and not (set(seq) & only):
            continue
        for ne in (1, 2):
            for f in (0, 6, 12):
                out.append({"kind": "card", "seq": list(seq), "up": False, "ne": ne, "fk": [f, 4][:ne], "blk": 7, "energy": 9})
    for seq in TURNS:
        if only and not (set(seq) & only):
            continue
        for ne in (1, 2):
            for f in (0, 6):
                out.append({"kind": "card", "seq": list(seq), "up": False, "ne": ne, "fk": [f, 4][:ne], "blk": 7,
                            "energy": 9, "turn": True})
    if not only:
        for n in (1, 2, 3):
            for cl in (0, 1, 2):          # 宪法分类器张数
                for am in (0, 50):
                    for dis in (0, 1):
                        for f in (0, 5, 12):
                            for h in (1, 3):
                                out.append({"kind": "hit", "n": n, "cl": cl, "am": am, "dis": dis, "fk": f, "h": h, "dmg": 6})
    return out


# ---------------------------------------------------------------- 旧引擎
def old_run(s, intents):
    from helpers import mods, enemy
    from sts2sim.core import Combat, Player, Card
    from sts2sim.relics import make_relic
    from sts2sim.ai import HeuristicAgent
    M = mods()
    P = Player("测试", 75, 3)
    ne = s.get("ne", 1)
    its = [tuple(x) for x in intents] + [(INTENT, 1)] * ne
    ens = [enemy(hp=ENEMY_HP, dmg=its[i][0], hits=max(1, its[i][1])) for i in range(ne)]
    C = Combat(P, ens, M, rng=random.Random(1), agent=HeuristicAgent())
    C.relics = [make_relic("CONSTITUTION")]
    P.draw_pile = [Card(M.find_card("小本本记下了"))] + [Card(M.find_card("打击")) for _ in range(9)]
    for e in C.enemies:
        e.setup(C)
    C.emit("battle_start")
    C.turn, C.phase = 1, "player"
    P.energy = 3
    for e, f in zip(C.enemies, s["fk"] if s["kind"] == "card" else [s["fk"]]):
        if f:
            C.set_stacks(e, "FK", f, op="setup")
    if s["kind"] == "card":
        seq = s.get("seq") or [s["cid"]]
        mine = [Card(M.find_card(CARDS[c]["name"]), s["up"]) for c in seq]
        P.hand = list(mine) + [Card(M.find_card("打击")) for _ in range(5)]
        P.block = s["blk"]
        P.energy = s.get("energy", 3)
        before = _old_snap(C)
        try:
            for card in mine:
                if card not in P.hand:
                    return {"error": "card left hand"}
                i = P.hand.index(card)
                t = C.enemies[0] if C.needs_target(card) else None
                C.play(i, t)
            if s.get("turn"):
                before = _old_snap(C)
                C.end_player_turn()
                C.enemy_phase()
                C.start_player_turn()
        except Exception as ex:   # noqa
            return {"error": f"{type(ex).__name__}: {ex}"[:200]}
        return _diff(before, _old_snap(C))
    # hit
    if s["n"]:
        C.apply_power(P, "CL_FANJI", s["n"], source=("op", "test"))
    for i in range(s["cl"]):
        if "CL_FENLEIQI" in P.powers:
            P.powers["CL_FENLEIQI"].data.setdefault("copies", [False]).append(False)
            P.powers["CL_FENLEIQI"].amount += 1
        else:
            C.apply_power(P, "CL_FENLEIQI", 1, source=("op", "test"))
            P.powers["CL_FENLEIQI"].data["copies"] = [False]
    if s["am"]:
        C.apply_power(P, "CL_XIUZHENG_C", s["am"], source=("op", "test"))
    if s["dis"]:
        C.apply_power(P, "CL_MIANZE", s["dis"], source=("op", "test"))
    before = _old_snap(C)
    e = C.enemies[0]
    for _ in range(s["h"]):
        C.deal_damage(e, P, s["dmg"], "attack")
    return _diff(before, _old_snap(C))


def _old_snap(C):
    P = C.player
    return {"ehp": [e.hp for e in C.enemies], "eblk": [e.block for e in C.enemies], "fk": [e.amt("FK") for e in C.enemies],
            "weak": [e.amt("WEAK") for e in C.enemies], "vuln": [e.amt("VULNERABLE") for e in C.enemies],
            "hp": P.hp, "blk": P.block, "en": P.energy, "hand": len(P.hand), "fanji": P.amt("CL_FANJI"), "str": P.amt("STRENGTH"),
            "npow": len([k for k in P.powers if k not in ("CL_FANJI",)])}


def _diff(a, b):
    return {"dmg": [x - y for x, y in zip(a["ehp"], b["ehp"])], "eblk": b["eblk"], "fk": b["fk"], "weak": b["weak"],
            "vuln": b["vuln"], "hp_loss": a["hp"] - b["hp"], "blk": b["blk"] - a["blk"], "en": b["en"] - a["en"],
            "hand": b["hand"] - a["hand"], "fanji": b["fanji"], "npow": b["npow"] - a["npow"], "str": b["str"]}


# ---------------------------------------------------------------- 新引擎
def new_run_all(scns, seed, variant=None):
    from claude_v35 import claude as CL
    CL.load(variant=variant)
    from sts2sim.rt.boot import game as G
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent
    results = {}

    def snap(cs, player, ens):
        pc = player.Creature

        def pw(cr, entry):
            for p in cr.Powers:
                if p.Id.Entry == entry:
                    return int(p.Amount)
            return 0
        return {"ehp": [e.CurrentHp for e in ens], "eblk": [e.Block for e in ens], "fk": [CL.fk(e) for e in ens],
                "weak": [pw(e, "WEAK_POWER") for e in ens], "vuln": [pw(e, "VULNERABLE_POWER") for e in ens],
                "hp": pc.CurrentHp, "blk": pc.Block, "en": player.PlayerCombatState.Energy, "hand": len(C.hand(player)),
                "fanji": pw(pc, "FANJI_POWER"), "str": pw(pc, "STRENGTH_POWER"), "npow": len([p for p in pc.Powers if p.Id.Entry != "FANJI_POWER"])}

    def setup(cs, player, s):
        ens = list(C.alive_enemies(cs))
        pc = player.Creature
        need = s.get("ne", 1)
        if len(ens) < need:
            raise RuntimeError("enemies")
        for e in ens[need:]:
            G.CreatureCmd.Kill(e)
        ens = ens[:need]
        for e in ens:
            for p in list(e.Powers):
                G.PowerCmd.Remove(p)
            e.SetMaxHpInternal(ENEMY_HP)
            e.SetCurrentHpInternal(ENEMY_HP)
            if e.Block:
                e.LoseBlockInternal(e.Block)
        for p in list(pc.Powers):
            G.PowerCmd.Remove(p)
        if pc.Block:
            pc.LoseBlockInternal(pc.Block)
        pc.SetCurrentHpInternal(75)
        player.PlayerCombatState.Energy = 3
        fks = s["fk"] if s["kind"] == "card" else [s["fk"]]
        for e, f in zip(ens, fks):
            if f:
                CL.set_fk(player, e, f)
        return ens

    class Agent(HeuristicAgent):
        def combat_action(self, cs, player, acts):
            ens = list(C.alive_enemies(cs))
            intents = []
            for e in ens:
                single, rep = 0, 0
                mv = e.Monster.NextMove
                for it in (mv.Intents if mv is not None else []):
                    if isinstance(it, G.AttackIntent):
                        single, rep = int(it.GetSingleDamage(G.Seq([player.Creature]), e)), int(it.Repeats)
                intents.append((single, rep))
            for i, s in enumerate(scns):
                r, w = os.pipe()
                pid = os.fork()
                if pid == 0:
                    os.close(r)
                    try:
                        out = run_one(cs, player, s)
                    except BaseException as ex:  # noqa
                        out = {"error": f"{type(ex).__name__}: {ex}"[:200]}
                    out["_intents"] = intents
                    os.write(w, json.dumps(out).encode())
                    os._exit(0)
                os.close(w)
                data = b""
                while True:
                    chunk = os.read(r, 65536)
                    if not chunk:
                        break
                    data += chunk
                os.close(r)
                os.waitpid(pid, 0)
                results[i] = json.loads(data or b'{"error":"child died"}')
            raise SystemExit(0)

    def run_one(cs, player, s):
        ens = setup(cs, player, s)
        pc = player.Creature
        if s["kind"] == "card":
            seq = s.get("seq") or [s["cid"]]
            for c in list(C.hand(player)):
                G.CardPileCmd.Add(c, G.PileType.Discard)
            mine = []
            for cid in seq:
                card = cs.CreateCard(G.ModelDb.Card(_g=(CL.CARD_CLASSES[cid],)), player)
                if s["up"]:
                    G.CardCmd.Upgrade(card)
                G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)
                mine.append(card)
            # 手牌：这些牌 + 5 张打击（与旧引擎一致）
            for _ in range(5):
                st = cs.CreateCard(G.ModelDb.Card(_g=(CL.CARD_CLASSES["CLAUDE_STRIKE"],)), player)
                G.CardPileCmd.AddGeneratedCardToCombat(st, G.PileType.Hand, player)
            G.CreatureCmd.GainBlock(pc, float(s["blk"]), G.ValueProp.Unpowered, None)
            player.PlayerCombatState.Energy = s.get("energy", 3)
            before = snap(cs, player, ens)
            for card in mine:
                if card not in list(C.hand(player)):
                    return {"error": "card left hand"}
                tgt = ens[0] if card.TargetType in (G.TargetType.AnyEnemy,) else None
                if not card.TryManualPlay(tgt):
                    return {"error": "not playable " + card.Id.Entry}
            if s.get("turn"):
                before = snap(cs, player, ens)
                r0 = cs.RoundNumber
                C.execute(("end",), cs, player)
                if cs.RoundNumber == r0:
                    return {"error": "turn did not advance"}
                ens = [e for e in ens]
            return _diff(before, snap(cs, player, ens))
        if s["n"]:
            CL.apply_power(pc, CL.FanjiPower, s["n"])
        for i in range(s["cl"]):
            CL.apply_power(pc, CL.ClassifierPower, 1)
            p = pc.GetPower(_g=(CL.ClassifierPower,))
            p._ms = getattr(p, "_ms", []) + [1.5]
        if s["am"]:
            CL.apply_power(pc, CL.AmendmentPower, s["am"])
        if s["dis"]:
            CL.apply_power(pc, CL.DisclaimerPower, s["dis"])
        before = snap(cs, player, ens)
        G.DamageCmd.Attack(float(s["dmg"])).FromMonster(ens[0].Monster).WithHitCount(s["h"]).Execute(None)
        return _diff(before, snap(cs, player, ens))

    try:
        R.play_run("Claude", 0, seed, agent=Agent())
    except SystemExit:
        pass
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--variant", default="v35_orig",   # 旧引擎 claude_v34 是 v3.5 原值；v3.5.1 只改了初始牌数值
                    help="新引擎用的变体（默认 v35_orig，和旧引擎数值一致）；传空字符串用 v3.5.1 默认值")
    ap.add_argument("--seed2", default="C9")     # 第一场是 2 名敌人的种子
    ap.add_argument("--out", default=os.path.join(ROOT, "reports/full_run/parity_v35.md"))
    ap.add_argument("--json", default=os.path.join(ROOT, "reports/full_run/parity_v35.json"))
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    scns = scenarios(only)
    new = new_run_all(scns, a.seed2, a.variant or None)
    rows, n_ok, n_diff, n_err = [], 0, 0, 0
    for i, s in enumerate(scns):
        nv = new.get(i, {"error": "missing"})
        intents = nv.pop("_intents", [])
        ov = old_run(s, intents)
        if "error" in nv or "error" in ov:
            n_err += 1
            rows.append((s, ov, nv, "error"))
            continue
        keys = [k for k in ov if ov[k] != nv.get(k) and (not s.get("turn") or k in TURN_KEYS)]
        if keys:
            n_diff += 1
            rows.append((s, ov, nv, keys))
        else:
            n_ok += 1
    json.dump([{"s": s, "old": o, "new": n, "diff": k} for s, o, n, k in rows], open(a.json, "w"), ensure_ascii=False, indent=0)
    print(f"scenarios {len(scns)}: same {n_ok}, differ {n_diff}, error {n_err}")
    by = {}
    for s, o, n, k in rows:
        key = ("+".join(s["seq"]) if s.get("seq") else s.get("cid")) if s["kind"] == "card" else "反击"
        by.setdefault(key, []).append((s, o, n, k))
    for key, lst in by.items():
        s, o, n, k = lst[0]
        print(f"  {key}: {len(lst)} 处不同；例 {s} → 差异 {k}\n      旧 {o}\n      新 {n}")


if __name__ == "__main__":
    main()
