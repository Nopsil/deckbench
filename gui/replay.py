"""Read a combat test's recorded loss timeline. Does not resimulate."""
from __future__ import annotations

import json
import os

from sts2sim.fighttrace import trace_status

MAX_LINE = 2_000_000


class ReplayError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _raw_path(run_dir):
    path = os.path.join(run_dir, "out", "raw.jsonl")
    if os.path.isfile(path) and not os.path.islink(path):
        return path
    alt = os.path.join(run_dir, "raw.jsonl")
    if os.path.isfile(alt) and not os.path.islink(alt):
        return alt
    return ""


def _rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if len(line) > MAX_LINE:
                raise ReplayError("big")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReplayError("read") from exc
            if not isinstance(row, dict):
                raise ReplayError("read")
            rows.append(row)
    return rows


def list_fights(run_dir):
    path = _raw_path(run_dir)
    if not path:
        raise ReplayError("nofile")
    out = []
    for index, row in enumerate(_rows(path)):
        out.append({
            "index": index,
            "deck": row.get("deck"),
            "encounter": row.get("encounter"),
            "enc_name": row.get("enc_name"),
            "result": row.get("result"),
            "turns": row.get("turns"),
            "hp_left": row.get("hp_left"),
            "hp_lost": row.get("hp_lost"),
            "trace": trace_status(row),
        })
    return {"fights": out, "losses": sum(1 for row in out if row["result"] == "loss")}


def load_trace(run_dir, index):
    path = _raw_path(run_dir)
    if not path:
        raise ReplayError("nofile")
    rows = _rows(path)
    if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(rows):
        raise ReplayError("fight")
    row = rows[index]
    status = trace_status(row)
    trace = row.get("trace") if isinstance(row.get("trace"), dict) else None
    return {
        "index": index,
        "deck": row.get("deck"),
        "encounter": row.get("encounter"),
        "enc_name": row.get("enc_name"),
        "result": row.get("result"),
        "turns": row.get("turns"),
        "hp_left": row.get("hp_left"),
        "hp_lost": row.get("hp_lost"),
        "status": status,
        "trace": trace if status in ("ready", "omitted") else None,
    }
