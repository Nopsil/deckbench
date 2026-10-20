"""Game-derived modules (game.py) are NOT in this repository.

They are generated locally from your own install by `python -m sts2sim.gamedata setup` and live in a
per-install cache. Importing `sts2sim.gen.game` verifies the cache against your install (path + SHA-256
of sts2.dll) and refuses to load on mismatch.
"""
from .. import gamedata as _gd

try:
    __path__.append(_gd.verify())  # noqa: F821  — 让 `import sts2sim.gen.game` 找到本机缓存里的 game.py
except _gd.GameDataError as _e:
    raise ModuleNotFoundError("sts2sim.gen.game 不可用 / not available:\n" + str(_e)) from None
