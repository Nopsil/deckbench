"""模仿学习：把“搜索 AI”的出牌决策蒸馏成一个快速打分模型（不需要 fork，Windows 可用）。

* 特征：每个候选动作一行（出牌/药水/结束回合），包括启发式自己的打分、伤害/格挡/击杀/来袭/血量/能量/房间类型等通用量，
  对新 mod 角色同样适用（不按卡名学）。
* 数据：learned-search 在需要搜索的决策点记录（候选特征, 搜索选中的动作）。`tools/imitate.py collect`。
* 模型：条件 logit（softmax 线性模型，L2），numpy 训练。`tools/imitate.py train` → data/imitation_model.json。
* 推理：ImitationAgent 在所有决策点用模型打分取最高；局外决策同 learned（StrongAgent + 学到的参数）。
"""
import json
import os

import numpy as np

from ..rt.boot import game as G
from .agents import _name, dvar, card_cost
from .combat import alive_enemies
from .strong import StrongAgent

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "imitation_model.json")

FEATS = ["is_end", "is_potion", "is_play", "heur", "heur_pos", "cost", "cost0", "dmg_frac", "kill", "kill_inc",
         "blk_use", "blk_over", "need_hp", "hp_frac", "power", "attack", "skill", "vuln", "weak", "strdex", "draw",
         "energy", "poison", "early", "elite", "boss", "en_left", "end_need", "end_energy", "slip_t", "minion_t",
         "n_en", "aoe", "hploss", "exhaust", "status", "pot_danger", "pot_boss", "inc_frac", "ehp_frac"]


def _kw(card):
    try:
        return {_name(k) for k in card.Keywords}
    except Exception:  # noqa
        return set()


def action_features(agent, cs, player, acts, ctx=None):
    """返回 (len(acts) × len(FEATS)) 特征矩阵。"""
    ctx = ctx or agent._make_ctx(cs, player)
    pc = player.Creature
    hp = max(1.0, float(pc.CurrentHp))
    mhp = max(1.0, float(pc.MaxHp))
    need = float(ctx["need"])
    en = alive_enemies(cs)
    ehp = ctx["ehp"]
    try:
        energy = float(player.PlayerCombatState.Energy)
    except Exception:  # noqa
        energy = 3.0
    room = getattr(agent, "room_kind", None)
    rows = []
    for a in acts:
        f = dict.fromkeys(FEATS, 0.0)
        f["need_hp"] = min(2.0, need / hp)
        f["hp_frac"] = hp / mhp
        f["early"] = 1.0 if cs.RoundNumber <= 2 else 0.0
        f["elite"] = 1.0 if room == "Elite" else 0.0
        f["boss"] = 1.0 if room == "Boss" else 0.0
        f["en_left"] = energy / 3.0
        f["n_en"] = len(en) / 3.0
        f["inc_frac"] = min(2.0, sum(ctx["inc"].values()) / hp)
        f["ehp_frac"] = min(3.0, ehp / mhp)
        if a[0] == "end":
            f["is_end"] = 1.0
            f["end_need"] = f["need_hp"]
            f["end_energy"] = energy / 3.0
        elif a[0] == "potion":
            f["is_potion"] = 1.0
            s = agent._score_potion(a[1], a[2], cs, player, need, hp)
            f["pot_danger"] = 1.0 if s > 0 and (need >= hp * 0.5 or hp <= mhp * 0.3) else 0.0
            f["pot_boss"] = 1.0 if room in ("Elite", "Boss") else 0.0
            f["heur"] = s / 6.0
        else:
            card, t = a[1], a[2]
            f["is_play"] = 1.0
            try:
                s = agent._score_play(card, t, cs, player, ctx)
            except Exception:  # noqa
                s = 0.0
            f["heur"] = max(-3.0, min(5.0, s / 4.0))
            f["heur_pos"] = 1.0 if s >= 0.03 else 0.0
            cost = card_cost(card)
            f["cost"] = cost / 3.0
            f["cost0"] = 1.0 if cost == 0 else 0.0
            dmg, hits, blk = agent._preview(card, t)
            d = dmg * hits
            if d > 0:
                tgt = t if t is not None else (en[0] if en else None)
                if tgt is not None:
                    eff = tgt.CurrentHp + tgt.Block
                    f["dmg_frac"] = min(1.5, d / max(1.0, ehp))
                    if d >= eff:
                        f["kill"] = 1.0
                        f["kill_inc"] = ctx["inc"].get(id(tgt), 0) / hp
                    f["slip_t"] = 1.0 if ctx["slip"].get(id(tgt)) else 0.0
                    f["minion_t"] = 1.0 if id(tgt) in ctx.get("minion", ()) else 0.0
            if blk > 0:
                f["blk_use"] = min(blk, need) / hp
                f["blk_over"] = max(0.0, blk - need) / 10.0
            tn = _name(card.Type)
            f["power"] = 1.0 if tn == "Power" else 0.0
            f["attack"] = 1.0 if tn == "Attack" else 0.0
            f["skill"] = 1.0 if tn == "Skill" else 0.0
            f["status"] = 1.0 if tn in ("Status", "Curse") else 0.0
            v = lambda k: dvar(card, k)  # noqa
            f["vuln"] = min(3.0, v("VulnerablePower")) / 3.0
            f["weak"] = min(3.0, v("WeakPower")) / 3.0
            f["strdex"] = min(3.0, v("StrengthPower") + v("DexterityPower") + v("FocusPower")) / 3.0
            f["draw"] = min(4.0, v("Cards")) / 4.0
            f["energy"] = min(3.0, v("Energy")) / 3.0
            f["poison"] = min(10.0, v("PoisonPower")) / 10.0
            f["hploss"] = min(10.0, v("HpLoss")) / 10.0
            f["aoe"] = 1.0 if card.TargetType == G.TargetType.AllEnemies else 0.0
            f["exhaust"] = 1.0 if "Exhaust" in _kw(card) else 0.0
        rows.append([f[k] for k in FEATS])
    return np.array(rows, dtype=np.float64)


# ---------- 数据记录 ----------
class Recorder:
    def __init__(self, path):
        self.path = path
        self.buf = []

    def add(self, X, y, meta):
        self.buf.append({"X": X.round(5).tolist(), "y": int(y), "m": meta})
        if len(self.buf) >= 50:
            self.flush()

    def flush(self):
        if not self.buf:
            return
        with open(self.path, "a") as f:
            for r in self.buf:
                f.write(json.dumps(r) + "\n")
        self.buf = []


class RecordingSearchAgent(StrongAgent):
    """learned-search，同时把搜索决策（顶层、非子进程）记下来。"""

    def __init__(self, recorder, **kw):
        super().__init__(**kw)
        self.recorder = recorder

    def combat_action(self, cs, player, acts):
        a = super().combat_action(cs, player, acts)
        if not self._in_child and len(acts) > 1 and getattr(self, "_searched", False):
            try:
                X = action_features(self, cs, player, acts)
                y = next(i for i, b in enumerate(acts) if b is a or b == a)
                self.recorder.add(X, y, [self.room_kind, cs.RoundNumber])
            except Exception:  # noqa
                pass
        self._searched = False
        return a

    def _eval_fork(self, *a, **k):
        self._searched = True
        return super()._eval_fork(*a, **k)


# ---------- 模型 ----------
_I = {k: i for i, k in enumerate(FEATS)}


def base_score(X):
    """启发式本身的决策规则写成分数：合格的出牌/药水 = 启发式分；结束回合 = 门槛；不合格 = −5。"""
    b = np.full(len(X), -5.0)
    play = (X[:, _I["is_play"]] > 0) & (X[:, _I["heur_pos"]] > 0)
    pot = (X[:, _I["is_potion"]] > 0) & (X[:, _I["heur"]] > 0.14)
    b[play | pot] = X[play | pot, _I["heur"]]
    b[X[:, _I["is_end"]] > 0] = 0.0075
    return b

def train(paths, l2=1e-3, iters=400, lr=0.05, val_frac=0.15, seed=0):
    data = []
    for p in paths:
        for line in open(p):
            r = json.loads(line)
            X = np.array(r["X"])
            y = r["y"]
            # 同名同目标的牌特征完全相同、效果等价：标签归到第一行（否则模型会被“选了第二张打击”罚分）
            y = int(np.flatnonzero((X == X[y]).all(1))[0])
            data.append((X, y, r["m"]))
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(data))
    nv = int(len(data) * val_frac)
    val = [data[i] for i in idx[:nv]]
    tr = [data[i] for i in idx[nv:]]
    allX = np.vstack([d[0] for d in tr])
    mu = allX.mean(0)
    sd = allX.std(0) + 1e-6
    # 参数：w[0] = 启发式规则分的倍数（从 10 开始 ≈ 完全照启发式），w[1:] = 在启发式之上的修正（从 0 开始）
    w = np.zeros(len(FEATS) + 1)
    w[0] = 150.0
    cache = {}

    def feats(X):
        k = id(X)
        if k not in cache:
            cache[k] = np.hstack([base_score(X)[:, None], (X - mu) / sd])
        return cache[k]

    def loss_grad(w, ds):
        L, g = 0.0, np.zeros_like(w)
        for X, y, _ in ds:
            Z = feats(X)
            s = Z @ w
            s -= s.max()
            p = np.exp(s)
            p /= p.sum()
            L -= np.log(p[y] + 1e-12)
            g += Z.T @ p - Z[y]
        n = max(1, len(ds))
        r = w.copy()
        r[0] = 0.0
        return L / n + l2 * (r @ r), g / n + 2 * l2 * r

    def acc(w, ds):
        return sum(int(np.argmax(feats(X) @ w) == y) for X, y, _ in ds) / max(1, len(ds))
    # Adam
    m = np.zeros_like(w)
    v = np.zeros_like(w)
    hist = [(0, acc(w, val))]
    best = (hist[0][1], w.copy())
    for t in range(1, iters + 1):
        L, g = loss_grad(w, tr)
        g[0] = 0.0          # 启发式规则分的倍数固定，只学修正项
        m = 0.9 * m + 0.1 * g
        v = 0.999 * v + 0.001 * g * g
        w -= lr * 0.1 * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
        if t % 25 == 0:
            va = acc(w, val)
            hist.append((t, L, va))
            if va > best[0]:
                best = (va, w.copy())
    w = best[1]
    return {"feats": ["base"] + FEATS, "w": w.tolist(), "mu": mu.tolist(), "sd": sd.tolist(), "n_train": len(tr), "n_val": len(val),
            "train_acc": acc(w, tr), "val_acc": acc(w, val), "loss_hist": hist}


def heuristic_agreement(paths):
    """基线：启发式首选和搜索选择一致的比例（在同样的数据上）。"""
    n = k = 0
    for p in paths:
        for line in open(p):
            r = json.loads(line)
            X = np.array(r["X"])
            r["y"] = int(np.flatnonzero((X == X[r["y"]]).all(1))[0])
            # 启发式 = 正分里 heur 最大的出牌/药水，否则结束回合
            hi = FEATS.index("heur")
            ok = [i for i in range(len(X)) if (X[i, FEATS.index("is_play")] and X[i, FEATS.index("heur_pos")]) or
                  (X[i, FEATS.index("is_potion")] and X[i, hi] > 0.14)]
            pick = max(ok, key=lambda i: X[i, hi]) if ok else len(X) - 1
            k += int(pick == r["y"])
            n += 1
    return k / max(1, n)


class ImitationAgent(StrongAgent):
    name = "imitation"

    def __init__(self, seed=0, model=None, **kw):
        kw["search"] = False
        super().__init__(seed=seed, **kw)
        m = model or json.load(open(MODEL))
        self._w = np.array(m["w"])
        self._mu = np.array(m["mu"])
        self._sd = np.array(m["sd"])

    def combat_action(self, cs, player, acts):
        if len(acts) <= 1:
            return acts[0]
        if self._in_child:
            return super().combat_action(cs, player, acts)
        X = action_features(self, cs, player, acts)
        s = np.hstack([base_score(X)[:, None], (X - self._mu) / self._sd]) @ self._w
        return acts[int(np.argmax(s))]
