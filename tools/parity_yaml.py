"""逐张牌对拍：手写 Python 版 Claude娘（mods/claude_v35）vs YAML 数据版（mods/claude_yaml）。

每张牌（普通 / 升级各一次）在同一个种子的第一场战斗里：先给敌人挂上风控（第 1 个 6 层、其余 3 层）、
给自己 10 点能量和 1 层反击，然后把这张牌加入手牌打出去（指向第 1 个敌人），记下局面；
再结束回合，等敌人打完、到下个回合开始再记一次（能力 / 遗物 / 反击的触发都在这里体现）。
两个版本各在自己的进程里跑（同一个进程不能同时注册两套同名的牌），最后逐项比较。

    PYTHONPATH=. python tools/parity_yaml.py            # 全部牌、种子 C1,C3,R7
    PYTHONPATH=. python tools/parity_yaml.py --only VERIFIED,FANJI
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def snapshot(G, cs, player):
    pc = player.Creature

    def pw(cr):
        return sorted((p.Id.Entry, int(p.Amount)) for p in cr.Powers)
    pcs = player.PlayerCombatState
    return {
        "player": [int(pc.CurrentHp), int(pc.Block), int(pcs.Energy), pw(pc)],
        "hand": [c.Id.Entry + ("+" if c.IsUpgraded else "") for c in G.PileType.Hand.GetPile(player).Cards],
        "piles": [len(list(getattr(G.PileType, k).GetPile(player).Cards)) for k in ("Draw", "Discard", "Exhaust")],
        "enemies": [[int(e.CurrentHp), int(e.Block), bool(e.IsAlive), pw(e)] for e in cs.Enemies],
    }


def child(mode, seeds, only):
    sys.path.insert(0, os.path.join(ROOT, "mods"))
    sys.path.insert(0, ROOT)
    from sts2sim.rt.boot import game as G
    if mode == "py":
        from claude_v35 import claude as CL
        CL.load()
        classes = dict(CL.CARD_CLASSES)
        fk_cls, fanji_cls = CL.FKPower, CL.FanjiPower
    else:
        from sts2sim.engine import yamlmod
        yamlmod.load(os.path.join(ROOT, "mods", "claude_yaml"))
        m = yamlmod.loaded()[-1]
        classes = dict(m.card_classes)
        fk_cls, fanji_cls = m.power_classes["FK"], m.power_classes["FANJI"]
    import sts2sim.engine.run as R
    import sts2sim.engine.combat as C
    from sts2sim.engine.agents import HeuristicAgent
    out = {}
    for cid in sorted(classes):
        if only and cid not in only:
            continue
        for up in (False, True):
            for seed in seeds:
                rec = {}

                class A(HeuristicAgent):
                    step = 0

                    def combat_action(self, cs, player, acts):
                        en = C.alive_enemies(cs)
                        if self.step == 0:
                            self.step = 1
                            for i, e in enumerate(en):
                                G.PowerCmd.Apply(G.ThrowingPlayerChoiceContext(), e, 6.0 if i == 0 else 3.0, player.Creature, None, _g=(fk_cls,))
                            G.PowerCmd.Apply(G.ThrowingPlayerChoiceContext(), player.Creature, 1.0, player.Creature, None, _g=(fanji_cls,))
                            G.PlayerCmd.GainEnergy(10.0, player)
                            card = cs.CreateCard(G.ModelDb.Card(_g=(classes[cid],)), player)
                            if up:
                                card.UpgradeInternal()
                            G.CardPileCmd.AddGeneratedCardToCombat(card, G.PileType.Hand, player)
                            self.card = card
                            rec["before"] = snapshot(G, cs, player)
                            tgt = en[0] if card.TargetType == G.TargetType.AnyEnemy else None
                            return ("play", card, tgt)
                        if self.step == 1:
                            self.step = 2
                            rec["after_play"] = snapshot(G, cs, player)
                            return ("end",)
                        rec["next_turn"] = snapshot(G, cs, player)
                        raise RuntimeError("stop")
                try:
                    R.play_run("Claude", 0, seed, agent=A())
                except Exception as e:  # noqa
                    rec["error"] = repr(e)[:200]
                out[f"{cid}{'+' if up else ''}@{seed}"] = rec
    json.dump(out, sys.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="C1,C3,R7")
    ap.add_argument("--only", default="")
    ap.add_argument("--child", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    seeds = a.seeds.split(",")
    only = {x for x in a.only.split(",") if x}
    if a.child:
        return child(a.child, seeds, only)
    res = {}
    procs = {m: subprocess.Popen([sys.executable, __file__, "--child", m, "--seeds", a.seeds, "--only", a.only],
                                 stdout=subprocess.PIPE, env=dict(os.environ, PYTHONPATH=ROOT)) for m in ("py", "yaml")}
    for m, p in procs.items():
        res[m] = json.loads(p.communicate()[0])
    keys = sorted(set(res["py"]) | set(res["yaml"]))
    same, diff = 0, []
    for k in keys:
        if res["py"].get(k) == res["yaml"].get(k):
            same += 1
        else:
            diff.append(k)
    cards = sorted({k.split("@")[0].rstrip("+") for k in keys})
    bad_cards = sorted({k.split("@")[0].rstrip("+") for k in diff})
    errs = sorted(k for k in keys if "error" in res["py"].get(k, {}) or "error" in res["yaml"].get(k, {}))
    print(f"场景 {len(keys)} 个（{len(cards)} 张牌 × 普通/升级 × {len(seeds)} 个种子）：一致 {same}，不一致 {len(diff)}")
    print(f"scenarios {len(keys)}: identical {same}, different {len(diff)}; cards with any difference: {len(bad_cards)} {bad_cards}")
    if errs:
        print("errors:", errs[:10])
    for k in diff[:8]:
        a_, b_ = res["py"].get(k), res["yaml"].get(k)
        for ph in ("before", "after_play", "next_turn", "error"):
            if (a_ or {}).get(ph) != (b_ or {}).get(ph):
                print(" ", k, ph, "\n    py  ", json.dumps((a_ or {}).get(ph), ensure_ascii=False)[:400],
                      "\n    yaml", json.dumps((b_ or {}).get(ph), ensure_ascii=False)[:400])
                break
    if a.out:
        json.dump({"same": same, "total": len(keys), "diff": diff, "cards": len(cards), "bad_cards": bad_cards, "res": res},
                  open(a.out, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
