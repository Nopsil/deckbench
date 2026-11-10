"""两份已保存的牌组预设对打。

共用第一份预设的遭遇、回合上限和种子（请求里写了才覆盖），
然后用界面已有的战斗测试各跑一遍。不另写一套出牌或播种。
"""
from sts2sim.deckpresets import DeckPresetError, head_to_head_plan

WAIT_SECS = 900


def run_pair(payload):
    """校验后开两场战斗测试，两场都结束后返回它们的 id。"""
    plan = head_to_head_plan(payload)
    from gui import i18n
    from gui.server import jobs

    params = {
        "seed": plan["seed"],
        "agent": plan["agent"],
        "procs": 1,
        "fights": 1,
        "max_turns": plan["max_turns"],
        "shared_plan": True,
        "encounters": plan["encounters"],
    }
    title_a = i18n.t("deck.h2hTitle", side="A", name=plan["title_a"])
    title_b = i18n.t("deck.h2hTitle", side="B", name=plan["title_b"])
    try:
        meta_a = jobs.start("combat", {**params, "preset": plan["a"]}, title_a)
    except ValueError as exc:
        raise DeckPresetError("preset") from exc
    try:
        meta_b = jobs.start("combat", {**params, "preset": plan["b"]}, title_b)
    except ValueError as exc:
        jobs.cancel(meta_a["id"])
        raise DeckPresetError("preset") from exc
    done_a = jobs.wait(meta_a["id"], WAIT_SECS)
    done_b = jobs.wait(meta_b["id"], WAIT_SECS)
    if not done_a or done_a.get("status") != "done" or not done_b or done_b.get("status") != "done":
        raise DeckPresetError("head_to_head")
    return {
        "ok": True,
        "a": done_a["id"],
        "b": done_b["id"],
        "seed": plan["seed"],
        "max_turns": plan["max_turns"],
        "agent": plan["agent"],
        "encounters": [row["id"] for row in plan["encounters"]],
        "fights": plan["fights"],
        "compare": "/#/compare?a=" + done_a["id"] + "&b=" + done_b["id"],
    }
