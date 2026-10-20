"""AI 可调参数（默认值 = 手工版；tools/tune_cma.py 用自我对局 + CMA-ES 学出来的版本存在 data/ai_weights.json）。

所有参数都是乘子或阈值，名字前缀：c_ 战斗出牌，d_ 选牌，m_ 路线，r_ 休息，s_ 商店，p_ 药水。
"""
import json
import os

DEFAULTS = {
    # 战斗（HeuristicAgent._score_play）
    "c_k": 1.0, "c_kill": 1.0, "c_blk": 1.0, "c_blk_over": 0.06, "c_power": 1.0, "c_vuln": 1.0, "c_weak": 1.0,
    "c_scal": 1.0, "c_draw": 1.8, "c_energy": 2.8, "c_minion": 1.0,
    # 药水
    "p_danger": 0.5, "p_lowhp": 0.3,
    # 选牌（StrongAgent.marginal / _threshold）
    "d_thr0": 0.5, "d_thr_slope": 0.1, "d_aoe": 0.5, "d_aoe_threat": 0.0, "d_aoe2": 0.0, "d_aoe_elite": 0.0, "d_atk1": 0.6, "d_atk": 0.4, "d_scal": 0.3,
    "d_syn": 0.3, "d_dup": 0.5,
    # 路线 / 休息 / 商店
    "m_elite_cost": 0.28, "m_elite_gain": 10.0, "m_weak_elite": 0.12, "m_rest_upg": 4.0, "m_unknown": 3.0,
    "r_heal": 0.45, "r_danger": 0.7, "s_margin": 0.6,
}
# CMA-ES 搜索时每个参数的尺度（≈ 合理变化幅度）
SCALE = {
    "c_k": 0.3, "c_kill": 0.3, "c_blk": 0.25, "c_blk_over": 0.05, "c_power": 0.4, "c_vuln": 0.4, "c_weak": 0.4,
    "c_scal": 0.4, "c_draw": 0.6, "c_energy": 0.8, "c_minion": 0.4, "p_danger": 0.15, "p_lowhp": 0.1,
    "d_thr0": 0.4, "d_thr_slope": 0.05, "d_aoe": 0.4, "d_aoe_threat": 0.5, "d_aoe2": 0.3, "d_aoe_elite": 0.5, "d_atk1": 0.4, "d_atk": 0.3, "d_scal": 0.3,
    "d_syn": 0.15, "d_dup": 0.3, "m_elite_cost": 0.08, "m_elite_gain": 4.0, "m_weak_elite": 0.08, "m_rest_upg": 2.0,
    "m_unknown": 1.5, "r_heal": 0.12, "r_danger": 0.12, "s_margin": 0.4,
}
W = dict(DEFAULTS)
LEARNED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ai_weights.json")


def set_weights(d):
    W.clear()
    W.update(DEFAULTS)
    W.update({k: float(v) for k, v in (d or {}).items() if k in DEFAULTS})


def load_learned(path=None):
    p = path or os.environ.get("STS2SIM_AI_WEIGHTS") or LEARNED
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    set_weights(d.get("weights", d))
    return W
