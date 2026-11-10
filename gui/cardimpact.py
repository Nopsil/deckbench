"""把一份已保存的牌组拆成基线和留一法变体，用现成的战斗测试逐个跑。

父任务负责进度和取消。每个变体是一场普通战斗测试，卡组 id、遭遇、种子和回合上限相同。
取消写在父任务上：正在打的那场打完，还没开始的不再派发。
"""
from __future__ import annotations

import json
import os
import threading

from sts2sim.cardimpact import build_report, plan_ablation
from sts2sim.deckpresets import MAX_BYTES, DeckPresetError

_REQUEST_KEYS = ("plus", "scale", "encounters", "gauntlet", "max_turns", "seed", "fights")
_RESULT_NAME = "card_impact.json"


def _jobs():
    from gui.server import jobs
    return jobs


def _lang():
    from gui import i18n
    return i18n.current()


def _safe(text):
    return str(text or "").replace("{", "(").replace("}", ")")


def _card_label(spec, lang):
    from gui import i18n
    if spec.get("change") == "baseline":
        return i18n.t("deck.impactBaseline", lang)
    if lang == "zhs":
        name = spec.get("name_zh") or spec.get("name") or spec.get("card_id") or ""
    else:
        name = spec.get("name_en") or spec.get("name") or spec.get("card_id") or ""
    if spec.get("upgrade") and name and not str(name).endswith("+"):
        name = str(name) + "+"
    return name or spec.get("card_id") or ""


def _child_title(spec, lang):
    from gui import i18n
    if spec.get("change") == "baseline":
        return i18n.t("deck.impactBaseline", lang)
    key = "deck.impactRemove" if spec.get("change") == "remove" else "deck.impactAdd"
    return i18n.t("deck.impactTitleCard", lang, change=i18n.t(key, lang), card=_safe(_card_label(spec, lang)))


def _stored_request(payload):
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in _REQUEST_KEYS if key in payload}


def _read_fights(run_dir):
    path = os.path.join(run_dir, "out", "raw.jsonl")
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_result(folder, doc):
    dest = os.path.join(folder, _RESULT_NAME)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)
        handle.write("\n")
    os.replace(tmp, dest)


def read_result(run_dir):
    if not run_dir:
        return None
    path = os.path.join(run_dir, _RESULT_NAME)
    if not os.path.isfile(path):
        return None
    try:
        if os.path.getsize(path) > MAX_BYTES * 8:
            return None
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _public_error(text, lang):
    from gui import i18n
    if not isinstance(text, str) or not text.strip() or "Traceback" in text:
        return i18n.t("deck.err.card_impact", lang)
    return text.strip().splitlines()[0][:240]


def _outcome(jobs, spec, run_id):
    meta = jobs.get(run_id) or {}
    folder = jobs.run_dir(run_id)
    fights = _read_fights(folder) if folder else []
    return {
        "id": run_id,
        "status": meta.get("status") or "",
        "fights": fights,
        "spec": spec,
    }


def _publish(job, plan, outcomes, *, status, partial):
    aligned = []
    for spec, outcome in zip(plan["variants"], outcomes):
        if outcome is None:
            aligned.append(None)
            continue
        aligned.append({"id": outcome["id"], "status": outcome["status"], "fights": outcome["fights"]})
    doc = build_report(plan, aligned, status=status, partial=partial)
    doc["id"] = job.meta.get("id")
    doc["job"] = job.meta.get("id")
    _write_result(job.dir, doc)
    return doc


def _parent_cancelled(job):
    from gui.jobs import cancel_requested
    return bool(job.cancelled or cancel_requested(job.dir))


def _run(job, plan, children):
    from gui import i18n
    jobs = _jobs()
    lang = job.meta.get("lang") or _lang()
    outcomes = [None] * len(children)
    done_fights = 0
    total = int(plan.get("total_fights") or 0)
    stopped = False
    failed = None
    try:
        for index, (spec, child) in enumerate(zip(plan["variants"], children)):
            if _parent_cancelled(job):
                stopped = True
                break
            label = _card_label(spec, lang)
            encounter = spec.get("card_id") or "baseline"
            jobs.update_progress(job, done_fights, total, encounter, label)
            jobs.log_line(job, i18n.t("deck.impactLog", lang, card=_safe(label)))
            if not jobs.launch(child.meta["id"]):
                meta = jobs.get(child.meta["id"]) or {}
                if meta.get("status") == "cancelled" or _parent_cancelled(job):
                    stopped = True
                    outcomes[index] = _outcome(jobs, spec, child.meta["id"])
                    break
                failed = _public_error(meta.get("error"), lang)
                outcomes[index] = _outcome(jobs, spec, child.meta["id"])
                break
            while True:
                meta = jobs.get(child.meta["id"]) or {}
                status = meta.get("status") or ""
                view = jobs.progress(child.meta["id"]) or {}
                child_done = int(view.get("done") or 0)
                jobs.update_progress(job, done_fights + child_done, total, encounter, label)
                if _parent_cancelled(job) and status in ("running", "queued"):
                    jobs.cancel(child.meta["id"])
                if status not in ("running", "queued"):
                    break
                threading.Event().wait(0.05)
            outcome = _outcome(jobs, spec, child.meta["id"])
            outcomes[index] = outcome
            done_fights += len(outcome["fights"])
            _publish(job, plan, outcomes, status="running", partial=_parent_cancelled(job))
            status = outcome["status"]
            if status == "failed":
                failed = _public_error((jobs.get(child.meta["id"]) or {}).get("error"), lang)
                break
            if status == "cancelled" or _parent_cancelled(job):
                stopped = True
                break
        for index, (child, outcome) in enumerate(zip(children, outcomes)):
            if outcome is None:
                jobs.drop_queued(child.meta["id"])
                outcomes[index] = _outcome(jobs, plan["variants"][index], child.meta["id"])
        partial = bool(stopped or failed)
        if failed:
            status = "failed"
        elif stopped:
            status = "cancelled"
        else:
            status = "done"
            partial = False
        doc = _publish(job, plan, outcomes, status=status, partial=partial or status == "cancelled")
        headline = {
            "fights": doc.get("fights"),
            "cards": len(doc.get("rows") or []),
            "partial": bool(doc.get("partial")),
        }
        if failed:
            headline["error"] = failed
        jobs.update_progress(job, done_fights, total, "", "")
        jobs.finish_local(
            job, status, partial=bool(doc.get("partial")), headline=headline, error=failed,
        )
        if status == "cancelled":
            jobs.log_line(job, i18n.t(
                "jobs.cancelled", lang, done=done_fights, total=total,
            ))
    except Exception as exc:  # noqa: BLE001
        message = _public_error(str(exc), lang)
        try:
            _publish(job, plan, outcomes, status="failed", partial=True)
        except OSError:
            message = i18n.t("deck.err.card_impact", lang)
        jobs.finish_local(job, "failed", partial=True, error=message)


def start(deck_id, payload=None):
    """校验后马上返回父任务 id 和每个变体的测试 id。不等它们打完。"""
    from gui import i18n
    plan = plan_ablation(deck_id, payload)
    lang = _lang()
    jobs = _jobs()
    request = _stored_request(payload if isinstance(payload, dict) else {})
    parent_params = {
        "deck": plan["deck"],
        "preset": plan["deck"],
        "seed": plan["seed"],
        "agent": plan["agent"],
        "max_turns": plan["max_turns"],
        "fights": plan["fights"],
        "total_fights": plan["total_fights"],
        "encounters": plan["encounters"],
        "plus": plan["plus"],
        "scale": plan["scale"],
        "scaled": plan["scaled"],
        "cap": plan["cap"],
        "request": request,
    }
    title = i18n.t("deck.impactTitle", lang, name=_safe(plan["title"]))
    parent = jobs.open_local("card_impact", parent_params, title=title, lang=lang, total=plan["total_fights"])
    children = []
    try:
        for spec in plan["variants"]:
            params = {
                "preset": plan["deck"],
                "seed": plan["seed"],
                "agent": plan["agent"],
                "procs": 1,
                "fights": 1,
                "max_turns": plan["max_turns"],
                "shared_plan": True,
                "encounters": plan["encounters"],
            }
            if spec.get("change") != "baseline":
                params["deck_cards"] = list(spec.get("cards") or [])
            child = jobs.prepare(
                "combat", params, title=_child_title(spec, lang), lang=lang, total=plan["fights"],
            )
            children.append(child)
    except DeckPresetError:
        jobs.finish_local(parent, "failed", error=i18n.t("deck.err.card_impact", lang))
        for child in children:
            jobs.drop_queued(child.meta["id"])
        raise
    except OSError as exc:
        jobs.finish_local(parent, "failed", error=i18n.t("deck.err.card_impact", lang))
        for child in children:
            jobs.drop_queued(child.meta["id"])
        raise DeckPresetError("card_impact") from exc
    runs = []
    outcomes = []
    for spec, child in zip(plan["variants"], children):
        runs.append({
            "id": child.meta["id"],
            "role": spec["role"],
            "change": spec["change"],
            "card_id": spec.get("card_id") or "",
            "upgrade": bool(spec.get("upgrade")),
            "status": "queued",
        })
        outcomes.append({"id": child.meta["id"], "status": "queued", "fights": []})
    doc = _publish(parent, plan, outcomes, status="running", partial=False)
    doc["runs"] = runs
    _write_result(parent.dir, doc)
    jobs.log_line(parent, title)
    threading.Thread(target=_run, args=(parent, plan, children), daemon=True).start()
    return {
        "ok": True,
        "id": parent.meta["id"],
        "job": parent.meta["id"],
        "status": "running",
        "deck": plan["deck"],
        "runs": runs,
        "seed": plan["seed"],
        "agent": plan["agent"],
        "max_turns": plan["max_turns"],
        "encounters": [row["id"] for row in plan["encounters"]],
        "fights": plan["fights"],
        "total_fights": plan["total_fights"],
        "scaled": plan["scaled"],
        "plus": plan["plus"],
        "cap": plan["cap"],
        "skipped": plan["skipped"],
    }


def _overlay(meta, doc):
    from gui.server import jobs
    view = dict(doc)
    view["ok"] = True
    view["id"] = meta.get("id")
    view["job"] = meta.get("id")
    view["status"] = meta.get("status") or view.get("status")
    view["partial"] = bool(meta.get("partial") or meta.get("status") == "cancelled" or view.get("partial"))
    view["deck"] = view.get("deck") or (meta.get("params") or {}).get("deck")
    runs = []
    for row in view.get("runs") or []:
        if not isinstance(row, dict):
            continue
        current = dict(row)
        live = jobs.get(current.get("id")) if current.get("id") else None
        if isinstance(live, dict) and live.get("status"):
            current["status"] = live.get("status")
        runs.append(current)
    view["runs"] = runs
    progress = jobs.progress(meta.get("id"))
    if progress:
        view["progress"] = progress
    return view


def _skeleton(meta):
    params = meta.get("params") if isinstance(meta.get("params"), dict) else {}
    runs = []
    for row in params.get("runs") or []:
        if isinstance(row, dict):
            runs.append(dict(row))
    return {
        "ok": True,
        "method": "leave_one_out",
        "id": meta.get("id"),
        "job": meta.get("id"),
        "deck": params.get("deck"),
        "status": meta.get("status"),
        "partial": bool(meta.get("partial") or meta.get("status") == "cancelled"),
        "plus": bool(params.get("plus")),
        "scale": True if "scale" not in params else bool(params.get("scale")),
        "scaled": bool(params.get("scaled")),
        "seed": params.get("seed"),
        "agent": params.get("agent"),
        "max_turns": params.get("max_turns"),
        "encounters": [row["id"] for row in params.get("encounters") or [] if isinstance(row, dict) and row.get("id")],
        "fights": params.get("fights"),
        "total_fights": params.get("total_fights"),
        "cap": params.get("cap"),
        "baseline": None,
        "rows": [],
        "skipped": [],
        "runs": runs,
    }


def view_meta(meta):
    if not isinstance(meta, dict):
        return None
    folder = _jobs().run_dir(meta.get("id"))
    doc = read_result(folder) if folder else None
    if doc is None:
        doc = _skeleton(meta)
    return _overlay(meta, doc)


def result_for_run(run_id):
    from sts2sim.deckpresets import _reject_path
    if not isinstance(run_id, str) or not run_id.strip():
        raise DeckPresetError("missing", field="run")
    text = run_id.strip()
    _reject_path(text)
    if text in (".", ".."):
        raise DeckPresetError("bad_id")
    meta = _jobs().get(text)
    if not isinstance(meta, dict):
        return None
    if meta.get("kind") != "card_impact":
        raise DeckPresetError("not_impact")
    return view_meta(meta)


def result_for_deck(deck_id):
    from sts2sim.cardimpact import _deck_id
    text = _deck_id(deck_id)
    jobs = _jobs()
    found = []
    seen = set()
    for meta in list(jobs.jobs.values()):
        if not isinstance(getattr(meta, "meta", None), dict):
            continue
        body = meta.meta
        if body.get("kind") != "card_impact":
            continue
        if (body.get("params") or {}).get("deck") != text:
            continue
        found.append(body)
        seen.add(body.get("id"))
    for body in jobs.list():
        if not isinstance(body, dict) or body.get("id") in seen:
            continue
        if body.get("kind") != "card_impact":
            continue
        if (body.get("params") or {}).get("deck") != text:
            continue
        found.append(body)
    if not found:
        return None
    found.sort(key=lambda row: row.get("created") or "", reverse=True)
    live = jobs.get(found[0].get("id"))
    return view_meta(live if isinstance(live, dict) else found[0])
