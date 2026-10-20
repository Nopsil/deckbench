"""跟踪一局：打印每场精英/首领战（或全部战斗）的逐回合决策。
python tools/trace_run.py --char Ironclad --asc 0 --seed R3 --agent strong-nosearch [--all]"""
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Ironclad")
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--seed", default="R0")
    ap.add_argument("--agent", default="strong-nosearch")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    import batch
    batch.AGENT.update({"name": a.agent, "kw": {}})
    batch._load_mods(a.char)
    from sts2sim.engine.run import play_run
    from sts2sim.engine.combat import alive_enemies, hand
    from sts2sim.engine.agents import _name
    ag = batch.make_agent(a.agent, a.seed)
    orig = ag.combat_action
    st = {"r": None}

    def ca(cs, player, acts):
        act = orig(cs, player, acts)
        if a.all or ag.room_kind in ("Elite", "Boss"):
            pc = player.Creature
            if st["r"] != (id(cs), cs.RoundNumber):
                st["r"] = (id(cs), cs.RoundNumber)
                en = "; ".join(f"{e.Monster.Id.Entry} {e.CurrentHp}hp b{e.Block} [{','.join(type(i).__name__.replace('Intent','') for i in e.Monster.NextMove.Intents) if e.Monster.NextMove else ''}] inc={ag._enemy_incoming(e, pc)} "
                               + ",".join(f"{p.Id.Entry[:-6]}{int(p.Amount)}" for p in e.Powers) for e in alive_enemies(cs))
                print(f"  R{cs.RoundNumber} HP {pc.CurrentHp}/{pc.MaxHp} blk {pc.Block} E{player.PlayerCombatState.Energy} | {en}")
                print("     hand:", ", ".join(c.Id.Entry + ("+" if c.IsUpgraded else "") for c in hand(player)),
                      "| pw:", ",".join(f"{p.Id.Entry[:-6]}{int(p.Amount)}" for p in pc.Powers))
            d = act[0] if act[0] == "end" else f"{act[0]} {act[1].Id.Entry} -> {act[2].Monster.Id.Entry if act[2] is not None and act[2].Monster is not None else ''}"
            print("     >", d, f"(E{player.PlayerCombatState.Energy} blk{pc.Block})")
        return act
    ag.combat_action = ca
    oc = ag.on_combat_start

    def ocs(cs, player, room):
        oc(cs, player, room)
        print(f"== F{ag._run.state.TotalFloor if hasattr(ag, '_run') else '?'} {ag.room_kind} {room.Encounter.Id.Entry if room.Encounter else ''} deck={len(list(player.Deck.Cards))}")
    ag.on_combat_start = ocs
    r = play_run(a.char, a.asc, a.seed, agent=ag)
    print("RESULT", r.victory, r.floor, r.death_room, r.error)
    print("deck", r.deck)
    print("relics", r.relics)
    print("path", r.path)


if __name__ == "__main__":
    main()
