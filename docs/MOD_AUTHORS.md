# Mod authors: getting started

[← README](../README.md) · [Index](INDEX.md) · [中文](MOD_AUTHORS.zh-CN.md) · [Format reference](MODDING.md)

This page is the short path from a fresh checkout to a number you can read. The example mod is `examples/spark/`. It is original YAML in the sts2sim mod format (`sts2sim/modfmt`). It adds two cards, **Arc** and **Lantern**, plus the small pool the full-run checker asks for (two Attacks, two Skills and one Power outside Basic, and at least one Common, Uncommon and Rare). Card text in that folder was written for this example.

The bash blocks below are what `tests/test_mod_authors.py` runs, in order, in one shell, from the repository root. The sample is two fights on purpose. A block tagged `needs-game` needs your own game install. The test skips those blocks. This repository does not contain game files, and the example does not either.

On Windows PowerShell, set the two variables first. The `python` lines are the same. If the `python` command is missing, use `python3`.

```powershell
$env:STS2SIM_USER_MODS = "examples"
$env:OUT = "$env:TEMP\deckbench-spark"
```

## Install

The internal Python fight engine (`python -m sts2sim`) only needs the Python dependencies. It does not read a game install.

```bash
python -m pip install -r requirements.txt
```

Generating local game data, the desktop app, and a full-run batch need the game installed and `python -m sts2sim.gamedata setup` already run. The test skips this:

```bash needs-game
python -m sts2sim.gamedata setup
```

## Load the example

The fight engine looks up a mod by folder name under `mods/`, then under each directory in `STS2SIM_USER_MODS` (separated by the OS path separator). `examples/spark` is the folder name `spark`.

```bash
export OUT="${OUT:-/tmp/deckbench-spark}"
export STS2SIM_USER_MODS=examples
mkdir -p "$OUT"
```

```bash
python - <<'PY'
from sts2sim.modfmt.schema import load_mod_dir, validate
mod = load_mod_dir("examples/spark")
problems, warnings = validate(mod, fullrun=True)
if problems:
    raise SystemExit("\n".join(f"{w}: {en}" for w, _zh, en in problems))
print(mod["name"], "cards", ",".join(c["id"] for c in mod["cards"]), "warnings", len(warnings))
PY
```

`problems` empty means the file is legal. The warnings are the pool-size reminders (fewer than three cards of a rarity). Types in `cards.yaml` use the Chinese words the internal engine matches (`攻击` / `技能` / `能力`). The checker also accepts `Attack` / `Skill` / `Power`.

`MATCH` is a relic in the file so you can see a trigger. The probe decks do not equip it. YAML relic and power triggers run in a full run, which is the `needs-game` section below. The fights on this page use the cards' damage and block ops.

## Win rate, with `--workers`

`examples/spark/winrate.yaml` fights the built-in training dummy (`encounter: DUMMY`). The dummy has 9999 HP and does not attack, so a one-turn fight times out. A timeout is not a win. `decks` is empty, so the file does not ask for a real encounter. The dummy row sets `fights: 2`. `--fights` sizes the `decks` list; that list is empty here, and the dummy row stays at 2.

`--workers 2` is the process count. It is the same switch as `--jobs`. Each fight's random numbers come from the seed, the deck, the act, the room and the fight index, so the process count does not change the result.

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --out "$OUT/win"
```

```bash
python - <<'PY'
import json
import os
out = os.environ["OUT"]
path = os.path.join(out, "win", "raw.jsonl")
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
from sts2sim.stats import format_win_rate, win_rate_report
wins = sum(r.get("result") == "win" for r in rows)
print(format_win_rate(win_rate_report(wins, len(rows)), "text"), end="")
meta = json.load(open(os.path.join(out, "win", "meta.json"), encoding="utf-8"))
print("workers", meta["jobs"])
PY
```

Read the text line:

- `胜率 / win rate: 0/2` is wins over fights. Both fights time out, so the rate is 0%.
- `Wilson 95% CI` is the interval. With two fights it is wide. The same line is what `tools/batch.py` prints for a full run.
- `样本不足，不能下结论 / sample too small to conclude: n=2 < 30` means the sample is below 30 valid fights. The numbers are still printed. They are not a verdict on Arc.
- `workers 2` is the process count recorded in `meta.json`.

`report.md` in that folder is the legacy fight report. Section 6 (coverage against a local monster codex) is skipped when that codex is absent, and the command still finishes. The codex is generated from your install and is not in this repository. Real rooms (`普通` / `精英` / `首领`) need it; this dummy sample does not.

## Card A/B

`examples/spark/ab.yaml` plays the same seeds twice: `spark_base` (Flick and Ward) and `spark_arc` (the same deck with one Flick replaced by Arc). B minus A is the card. `spark_lantern` is in `decks.yaml` for the same swap with Lantern; this sample does not run it.

```bash
python -m sts2sim examples/spark/ab.yaml --workers 2 --fights 2 --seed 1 --out "$OUT/ab"
```

```bash
python - <<'PY'
import json
import os
path = os.path.join(os.environ["OUT"], "ab", "raw.jsonl")
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
from sts2sim.stats import ab_win_report, format_ab

def tally(deck):
    group = [r for r in rows if r["deck"] == deck]
    return sum(r.get("result") == "win" for r in group), len(group)

base_w, base_n = tally("spark_base")
arc_w, arc_n = tally("spark_arc")
print(format_ab(ab_win_report(base_w, base_n, arc_w, arc_n), "text"), end="")
PY
```

Read that block. It is the same formatter `tools/ab_card.py --format text` uses:

- Each side has its own `Wilson 95% CI`.
- `两比例 z 检验 / two-proportion z-test` is a pooled two-sided z-test. `p=` is the p-value for "the two win rates are the same". `B − A` is Arc's win rate minus the baseline win rate. The paired difference that full runs also print is a separate number; this line is the marginal win-rate test.
- On this dummy both sides are 0/2, so the difference is 0% and `p=1.0000`.
- `n=2 and n=2 < 30` is the small-sample warning. It is printed whenever either side has fewer than 30 valid fights, including when `p` is small. A warning means you do not conclude.

A full run of the same mod, once you have generated local game data, is the command the test skips. `--force SPARK_ARC` is the id pattern from [MODDING.md](MODDING.md): prefix `Spark` plus card id `ARC`. The mod editor shows the id the game registered; use that string if a run says the card is missing. `--n 200` is a starting size at which the warning is quiet (the cutoff is 30). It is still an AI win rate, for comparing settings, not a player win rate.

```bash needs-game
python tools/batch.py --mod examples/spark --char Wick --asc 0 --n 200 --agent modai --workers 2
python tools/ab_card.py --mod examples/spark --char Wick --asc 0 --n 200 --agent modai --workers 2 --force SPARK_ARC --format text
```

## Why the AI played a card

`--explain` writes `explain.jsonl` next to the report. It records candidates the AI had already scored. It does not draw extra random numbers. `--workers` can stay on; each fight still carries its own rows.

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --explain --out "$OUT/explain"
python tools/explain_fight.py "$OUT/explain/explain.jsonl" --fight 0
```

`tools/explain_fight.py --fight 0` prints the first fight as Markdown (fights are numbered from 0 after the optional `--seed` filter). For this deck the first **出牌 / play** block chooses **Arc**. The table under it lists the other cards in hand and their scores. `←` marks the one played. Arc is chosen because the position after playing it scores higher than Flick or Ward. Later blocks in the same turn play Flick until energy runs out; the last block is the end of the turn.

## Optional `--mechanic-aware`

Off by default, including when you omit the flag. `--mechanic-aware` turns on the heuristic adjustment for thorns, block gained when hit, and the sum of incoming damage. `--no-mechanic-aware` keeps it off. With the flag on, an `--explain` candidate can carry a `note` of `thorns:`, `armour` or `incoming:`.

The training dummy has no thorns and does not attack, so this sample's notes do not contain those words, and the cards played match the run without the flag. Use the flag when the fight actually has those mechanics. Real encounters need the local monster codex; the test does not run those.

```bash
python -m sts2sim examples/spark/winrate.yaml --workers 2 --fights 2 --seed 1 --mechanic-aware --explain --out "$OUT/mechanic"
python tools/explain_fight.py "$OUT/mechanic/explain.jsonl" --fight 0
```

```bash
python - <<'PY'
import json
import os
meta = json.load(open(os.path.join(os.environ["OUT"], "mechanic", "meta.json"), encoding="utf-8"))
print("mechanic_aware", meta["exp"]["agent_kw"]["mechanic_aware"])
PY
```

`mechanic_aware True` is the flag stored on the experiment. The explain Markdown above is how you read the choice.

## What stays out of the repo

Ship your own card text and numbers. Do not add game files, extracted tables, or copied card text. [CONTRIBUTING.md](../CONTRIBUTING.md) is the rule. The format for a larger mod is [MODDING.md](MODDING.md).
