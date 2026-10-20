"""spire-mentor 事件 PPO 需要的英文选项文本：运行时从玩家本机的游戏安装读（sts2sim/gameloc.py），绝不进仓库。
读不到时返回 None，调用方回退到我们自己的策略。"""
import re

from .. import gameloc

_RE_VAR = re.compile(r"\{(\w+)(?::[^{}]*)?\}")


def _vars(model):
    out = {}
    try:
        dv = model.DynamicVars
        for k in list(dv.Keys):
            try:
                var = dv[k]
                tn = type(var).__name__
                if any(x in tn for x in ("Potion", "Relic", "Card", "Enchant", "String", "Model")):
                    continue   # 名字类变量：没有显示名，保留占位符
                out[str(k)] = int(var.IntValue)
            except Exception:  # noqa
                pass
    except Exception:  # noqa
        pass
    return out


def resolve(text, model):
    """把 {Name} / {Name:fmt} 换成 model.DynamicVars[Name] 的整数值；不认识的占位符保持原样。"""
    if not text:
        return ""
    v = _vars(model)
    return _RE_VAR.sub(lambda m: str(v[m.group(1)]) if m.group(1) in v else m.group(0), text)


def event_option_text(event, option):
    """(title, description) 或 None。"""
    t = gameloc.table("events", "eng")
    key = str(getattr(option, "TextKey", "") or "")
    if not t or not key:
        return None
    title, desc = t.get(key + ".title"), t.get(key + ".description")
    if title is None and desc is None:
        return None
    return resolve(title or "", event), resolve(desc or "", event)
