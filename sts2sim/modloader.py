"""加载 mod：mods/<名字>/mod.yaml + cards.yaml + decks.yaml + hooks.py。

mod.yaml 例：
  name: claude_v34
  title: Claude娘 v3.4
  cards: [cards.yaml]
  decks: [decks.yaml]
  hooks: hooks.py
  characters:
    claude: {name: Claude娘, hp: 75, energy: 3, hand: 5, relics: [CONSTITUTION]}
  ai_values: {FK: 0.8}        # 可选：给启发式 AI 的能力估值覆盖
"""
import importlib.util
import os
import yaml
from .cards import CardDef
from .core import Player, Card
from .relics import make_relic
from . import powers as _powers  # noqa: 注册通用能力
from . import enemies as _enemies  # noqa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS_DIR = os.path.join(ROOT, "mods")
BUILTIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin_cards.yaml")


def _yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class ModSet:
    def __init__(self, names):
        self.names = list(names)
        self.cards = {}
        self.by_name = {}
        self.characters = {}
        self.decks = {}
        self.listeners = []
        self.hook_modules = []
        self.ai_values = {}
        self.meta = {}
        self._load_cards(_yaml(BUILTIN), "builtin")
        for n in self.names:
            self._load_mod(n)

    def _load_cards(self, lst, mod_name):
        for raw in lst or []:
            d = CardDef(raw, mod_name)
            self.cards[d.id] = d
            self.by_name.setdefault(d.name, d)

    def _load_mod(self, name):
        base = os.path.join(MODS_DIR, name)
        meta = _yaml(os.path.join(base, "mod.yaml"))
        self.meta[name] = meta
        if meta.get("hooks"):
            path = os.path.join(base, meta["hooks"])
            spec = importlib.util.spec_from_file_location(f"mods_{name}_hooks", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.hook_modules.append(mod)
            if getattr(mod, "LISTEN", True):
                self.listeners.append(mod)
        for f in meta.get("cards") or []:
            self._load_cards(_yaml(os.path.join(base, f)), name)
        for cid, ch in (meta.get("characters") or {}).items():
            ch = dict(ch)
            ch["mod"] = name
            self.characters[cid] = ch
        if meta.get("potions"):
            from .potions import register_potions
            from .catalog import codex_index
            for f in meta["potions"]:
                register_potions(_yaml(os.path.join(base, f)), name, codex_index("potions"))
        for f in meta.get("decks") or []:
            for dk in _yaml(os.path.join(base, f)) or []:
                dk = dict(dk)
                dk["mod"] = name
                self.decks[dk["id"]] = dk
        self.ai_values.update(meta.get("ai_values") or {})

    def call(self, fn, *a, **k):
        for m in self.hook_modules:
            f = getattr(m, fn, None)
            if f is not None:
                return f(*a, **k)
        raise KeyError(f"hooks 里找不到函数 {fn}")

    def find_card(self, key):
        if key in self.cards:
            return self.cards[key]
        if key in self.by_name:
            return self.by_name[key]
        raise KeyError(f"找不到卡 {key}")

    def parse_deck(self, items):
        """「打击×4」「已核实+」「防御*2」→ [(CardDef, upgraded)]。"""
        out = []
        for it in items:
            s = str(it).strip()
            n = 1
            for sep in ("×", "*", " x"):
                if sep in s:
                    s, k = s.rsplit(sep, 1)
                    n = int(k)
                    s = s.strip()
                    break
            up = s.endswith("+")
            if up:
                s = s[:-1]
            d = self.find_card(s)
            out += [(d, up)] * n
        return out

    def build_player(self, deck_id):
        dk = self.decks[deck_id]
        ch = self.characters[dk["character"]]
        P = Player(ch.get("name", dk["character"]), ch.get("hp", 75), ch.get("energy", 3), ch.get("hand", 5),
                   ch.get("orb_slots", 0))
        cards = self.parse_deck(dk["cards"])
        n_up = dk.get("auto_upgrade", 0)
        if n_up:
            # 自动升级：按卡表顺序升级前 N 张非基础牌（每个名字一次）
            done = set(self.find_card(n).id for n in (dk.get("keep_base") or []))   # keep_base：这些牌保持未升级
            n_up -= len(done & {d.id for d, _ in cards})       # 仍占升级名额，其余牌的升级与原卡组一致
            for i, (d, up) in enumerate(cards):
                if n_up <= 0:
                    break
                if d.rarity != "基础" and not up and d.id not in done:
                    cards[i] = (d, True)
                    done.add(d.id)
                    n_up -= 1
        P.draw_pile = [Card(d, up) for d, up in cards]
        P.potions = list(dk.get("potions") or [])
        relics = dk.get("relics", ch.get("relics", []))
        return P, [make_relic(r) for r in relics], dk
