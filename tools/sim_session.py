"""一局交互式模拟的子进程（MCP 服务器每局开一个；也可以直接手动用）。

  python tools/sim_session.py --char Ironclad --asc 10 --seed Q1ANWENN1ANG --log run/decisions.jsonl [--replay run/choices.json]
协议：stdout 一行一个 JSON（引擎自己的打印都转到 stderr）：
  子→父 {"type":"decision", n, screen, text, options, enabled, multi, error}
         {"type":"ack", n, choice, reason, source, label}
         {"type":"end", victory, floor, …} / {"type":"fatal", error}
  父→子 {"choice": i 或 [i…], "reason": "…"} 或 {"auto": true}
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="Ironclad")
    ap.add_argument("--asc", type=int, default=0)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--replay", default="")
    ap.add_argument("--persona", default="")
    ap.add_argument("--fallback", default="learned")
    ap.add_argument("--style", default="", help="打法风格：auto 代打用的风格（standard / juggler，见 sts2sim/engine/style.py）")
    a = ap.parse_args()
    out = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr
    inp = sys.stdin

    def io(d):
        if "ack" in d:
            out.write(json.dumps({"type": "ack", **{("n" if k == "ack" else k): v for k, v in d.items()}}, ensure_ascii=False) + "\n")
            return None
        out.write(json.dumps({"type": "decision", **d}, ensure_ascii=False) + "\n")
        while True:
            line = inp.readline()
            if not line:
                raise SystemExit(0)
            msg = json.loads(line)
            if "cmd" not in msg:
                return msg
            try:
                out.write(json.dumps({"type": "info", "cmd": msg["cmd"], "text": info(msg["cmd"])}, ensure_ascii=False) + "\n")
            except Exception as e:  # noqa
                out.write(json.dumps({"type": "info", "cmd": msg["cmd"], "text": f"出错：{e}"}, ensure_ascii=False) + "\n")

    holder = {}

    def info(cmd):
        drv = holder["drv"]
        st = drv.state
        if cmd == "map":
            import seed_probe as SP
            from sts2sim.rt.boot import game as G
            mp = SP._map(G, st)
            cur = st.CurrentMapPoint
            pos = f"当前位置：第{int(cur.coord.row)}行 第{int(cur.coord.col)}列" if cur is not None else "当前位置：还没出发（第 0 行起点）"
            vis = "、".join(f"({int(c.row)},{int(c.col)})" for c in st.VisitedMapCoords) if hasattr(st, "VisitedMapCoords") else ""
            return f"第{int(st.CurrentActIndex) + 1}幕地图（上 = 首领，下 = 第 1 行；怪=普通 精=精英 ？=未知 商=商店 火=休息 宝=宝箱）\n" \
                + SP.render_map(mp) + "\n" + pos + (f"\n走过的点(行,列)：{vis}" if vis else "")
        if cmd == "deck":
            from sts2sim.engine import textstate as T
            return "\n".join(f"{i}. {T.card_line(c)}" for i, c in enumerate(drv.player.Deck.Cards))
        raise ValueError(cmd)

    try:
        from sts2sim.engine.seed import canonicalize
        from sts2sim.engine.interactive import InteractiveAgent
        from sts2sim.engine.decision_log import DecisionLogger
        from sts2sim.engine.run import RunDriver
        import batch
        seed = canonicalize(a.seed)
        replay = json.load(open(a.replay, encoding="utf-8")) if a.replay else []
        fb = batch.make_agent(a.fallback, seed) if a.fallback else None
        if fb is not None and a.style:
            from sts2sim.engine.style import apply_style
            try:
                fb = apply_style(fb, a.style, a.fallback)
            except ValueError as e:   # 旧存档里的风格 id 不认识了：按标准打，不中断
                print("style:", e, "-> standard", file=sys.stderr)
        ag = InteractiveAgent(io, replay=replay, fallback=fb, persona=a.persona or None)
        lg = DecisionLogger(ag, a.log, agent_name="mcp", meta={"seed": seed, "char": a.char, "asc": a.asc})
        drv = RunDriver(a.char, a.asc, seed, agent=lg)
        holder["drv"] = drv
        r = drv.play()
        lg.close()
        d = r.to_dict()
        out.write(json.dumps({"type": "end", "victory": d["victory"], "floor": d["floor"], "act": d["act"], "hp": d["hp"],
                              "max_hp": d["max_hp"], "gold": d["gold"], "deck": d["deck"], "relics": d["relics"],
                              "death_room": d["death_room"], "error": d["error"]}, ensure_ascii=False, default=str) + "\n")
    except SystemExit:
        raise
    except BaseException as e:  # noqa
        import traceback
        out.write(json.dumps({"type": "fatal", "error": f"{type(e).__name__}: {e}\n" + traceback.format_exc()[-1500:]}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
