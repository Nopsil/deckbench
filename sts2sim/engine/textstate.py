"""把局面压成给人/LLM 看的简短中文文本（MCP 接口和以后的 LLM agent 共用）。

中文名和卡牌说明运行时从玩家本机的游戏安装读（sts2sim/gameloc.py，只在内存里），
不进仓库、不打包；读不到就显示 ID。
"""
import re

from ..rt.boot import game as G

_LOC = {}
_RE_TAG = re.compile(r"\[/?[a-z_]+(?:=[^\]]*)?\]")
_RE_VAR = re.compile(r"\{(\w+)(?::[^{}]*)?\}")


def loc(table):
    if table not in _LOC:
        from .. import gameloc
        _LOC[table] = gameloc.table(table, "zhs") or {}
    return _LOC[table]


def zh(table, key, field="title"):
    v = loc(table).get(f"{key}.{field}")
    return v if isinstance(v, str) else None


def _n(e):
    try:
        return e.name
    except AttributeError:
        return str(e).split(".")[-1]


def _vars(model):
    out = {}
    try:
        dv = model.DynamicVars
        for k in list(dv.Keys):
            try:
                out[str(k)] = int(dv[k].IntValue)
            except Exception:  # noqa
                pass
    except Exception:  # noqa
        pass
    return out


def render_text(text, model=None):
    if not text:
        return ""
    v = _vars(model) if model is not None else {}
    text = _RE_VAR.sub(lambda m: str(v[m.group(1)]) if m.group(1) in v else "X", text)
    return _RE_TAG.sub("", text).replace("\n", " ")


# ---------------- 卡牌 ----------------
_CARD_CACHE = {}


def card_name(c):
    c = getattr(c, "Card", c) if not isinstance(c, G.CardModel) else c
    try:
        cid = c.Id.Entry
    except Exception:  # noqa
        return str(c)
    return (zh("cards", cid) or cid) + ("+" if getattr(c, "IsUpgraded", False) else "")


def card_cost(c):
    try:
        x = c.EnergyCost
        if getattr(x, "CostsX", False):
            return "X"
        return str(int(x.GetResolved()))
    except Exception:  # noqa
        try:
            return str(int(c.EnergyCost.Canonical))
        except Exception:  # noqa
            return "?"


def card_desc(c):
    """说明文字（缓存：同一 ID+升级+数值只算一次）。"""
    c = getattr(c, "Card", c) if not isinstance(c, G.CardModel) else c
    try:
        cid = c.Id.Entry
    except Exception:  # noqa
        return ""
    v = _vars(c)
    key = (cid, bool(getattr(c, "IsUpgraded", False)), tuple(sorted(v.items())))
    if key not in _CARD_CACHE:
        _CARD_CACHE[key] = render_text(zh("cards", cid, "description") or "", c)
    return _CARD_CACHE[key]


def card_line(c, desc=True):
    c = getattr(c, "Card", c) if not isinstance(c, G.CardModel) else c
    s = f"{card_name(c)}({card_cost(c)}费 {_TYPE.get(_n(c.Type), _n(c.Type))}"
    try:
        r = _n(c.Rarity)
        if r not in ("Basic", "None"):
            s += " " + _RAR.get(r, r)
    except Exception:  # noqa
        pass
    s += ")"
    if desc:
        d = card_desc(c)
        if d:
            s += "：" + d
    return s


_TYPE = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Status": "状态", "Curse": "诅咒", "Quest": "任务"}
_RAR = {"Common": "普通", "Uncommon": "罕见", "Rare": "稀有", "Ancient": "先古", "Event": "事件", "Token": "衍生",
        "Status": "状态", "Curse": "诅咒"}
POINT_ZH = {"Monster": "普通怪", "Elite": "精英", "Unknown": "未知", "Shop": "商店", "RestSite": "休息处", "Treasure": "宝箱",
            "Boss": "首领", "Ancient": "先古"}


def relic_name(r):
    try:
        return zh("relics", r.Id.Entry) or r.Id.Entry
    except Exception:  # noqa
        return str(r)


def potion_name(p):
    try:
        return zh("potions", p.Id.Entry) or p.Id.Entry
    except Exception:  # noqa
        return str(p)


def power_list(creature):
    out = []
    try:
        for p in creature.Powers:
            pid = p.Id.Entry
            out.append(f"{zh('powers', pid) or pid}{int(p.Amount)}")
    except Exception:  # noqa
        pass
    return out


def monster_name(cr):
    try:
        mid = cr.Monster.Id.Entry
        return zh("monsters", mid, "name") or zh("monsters", mid) or mid
    except Exception:  # noqa
        return "?"


def intent_text(e, player):
    out = []
    try:
        for it in e.Monster.NextMove.Intents:
            t = type(it).__name__.replace("Intent", "")
            if isinstance(it, G.AttackIntent):
                try:
                    dmg = int(it.GetTotalDamage(G.Seq([player.Creature]), e))
                    hits = int(getattr(it, "Repeats", 1) or 1)
                    out.append(f"攻击{dmg}" + (f"(共{hits}段)" if hits > 1 else ""))
                    continue
                except Exception:  # noqa
                    pass
            out.append(_INT.get(t, t))
    except Exception:  # noqa
        pass
    return "、".join(out) or "?"


_INT = {"Defend": "防御", "Buff": "强化", "Debuff": "削弱", "DebuffStrong": "强削弱", "Escape": "逃跑", "Sleep": "睡觉",
        "Stun": "眩晕", "Unknown": "未知", "Summon": "召唤", "StatusCard": "塞状态牌", "Heal": "治疗", "CardDebuff": "卡牌削弱"}


# ---------------- 整体 ----------------
def header(run):
    st, p = run.state, run.player
    cr = p.Creature
    L = [f"第{int(st.CurrentActIndex) + 1}幕 第{int(st.TotalFloor)}层 | HP {int(cr.CurrentHp)}/{int(cr.MaxHp)} | 金币 {int(p.Gold)}"
         f" | {run.character} A{run.ascension} | 种子 {run.seed}"]
    L.append("遗物：" + ("、".join(relic_name(r) for r in p.Relics) or "无"))
    pots = []
    try:
        for x in p.PotionSlots:
            pots.append(potion_name(x) if x is not None else "空")
    except Exception:  # noqa
        pots = [potion_name(x) for x in p.Potions if x is not None]
    L.append("药水：" + ("、".join(pots) or "无"))
    cnt = {}
    for c in p.Deck.Cards:
        k = card_name(c)
        cnt[k] = cnt.get(k, 0) + 1
    L.append(f"牌组({sum(cnt.values())})：" + "、".join(k + (f"×{n}" if n > 1 else "") for k, n in cnt.items()))
    return "\n".join(L)


def pile_count(pt, player):
    try:
        return len(list(pt.GetPile(player).Cards))
    except Exception:  # noqa
        return "?"


def combat_block(cs, player):
    pcs = player.PlayerCombatState
    cr = player.Creature
    L = []
    try:
        en = f"{int(pcs.Energy)}/{int(pcs.MaxEnergy)}"
    except Exception:  # noqa
        en = str(int(pcs.Energy))
    pw = power_list(cr)
    L.append(f"战斗 第{int(cs.RoundNumber)}回合 | 能量 {en} | 格挡 {int(cr.Block)}" + (" | 能力：" + "、".join(pw) if pw else ""))
    L.append(f"抽牌堆 {pile_count(G.PileType.Draw, player)} | 弃牌堆 {pile_count(G.PileType.Discard, player)}"
             f" | 消耗堆 {pile_count(G.PileType.Exhaust, player)}")
    L.append("手牌：")
    for i, c in enumerate(G.PileType.Hand.GetPile(player).Cards):
        L.append(f"  h{i} {card_line(c)}")
    L.append("敌人：")
    for k, e in enumerate(cs.Enemies):
        if not e.IsAlive:
            continue
        pw = power_list(e)
        L.append(f"  #{k} {monster_name(e)} HP {int(e.CurrentHp)}/{int(e.MaxHp)} 格挡 {int(e.Block)} | 意图：{intent_text(e, player)}"
                 + (" | 能力：" + "、".join(pw) if pw else ""))
    return "\n".join(L)


def target_name(t, cs):
    if t is None:
        return ""
    try:
        if t.Monster is not None:
            k = [x for x in cs.Enemies].index(t)
            return f" → #{k} {monster_name(t)}"
    except Exception:  # noqa
        pass
    return " → 自己"


def action_label(a, cs, player):
    if a[0] == "end":
        return "结束回合"
    if a[0] == "play":
        hand = list(G.PileType.Hand.GetPile(player).Cards)
        hi = next((i for i, c in enumerate(hand) if c is a[1]), "?")
        return f"打出 h{hi} {card_name(a[1])}({card_cost(a[1])}费){target_name(a[2], cs)}"
    if a[0] == "potion":
        return f"使用药水 {potion_name(a[1])}{target_name(a[2], cs)}"
    return str(a)
