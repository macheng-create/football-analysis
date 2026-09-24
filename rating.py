# -*- coding: utf-8 -*-
"""rating.py - 评分模型（含赔率变化追踪）"""


def calc_rating(row):
    if not row:
        return None

    has_traj = row.get("has_trajectory", False)
    score = 50.0
    details = []

    # 1. 基础分（盘口轨迹 或 隐含概率）
    if has_traj:
        sig = row.get("sig", 0.0) or 0.0
        score += sig * 30
        details.append(f"轨迹{sig:+.2f}")
    else:
        lo = row.get("live_over")
        lu = row.get("live_under")
        if lo and lu and lo > 1.01 and lu > 1.01:
            p_over = (1.0 / lo) / (1.0 / lo + 1.0 / lu)
            score = p_over * 100
            details.append(f"隐含{p_over:.1%}")

    # 2. 赔率变化（如果有多快照）⭐ 新增
    move_sig = row.get("movement_signal")
    if move_sig is not None and abs(move_sig) > 0.05:
        score += move_sig * 20  # 权重 40%
        details.append(f"变化{move_sig:+.2f}")

    # 3. 天气
    w_over = row.get("weather_over_bonus", 0) or 0
    w_under = row.get("weather_under_bonus", 0) or 0
    if w_over or w_under:
        score += w_over - w_under
        details.append(f"天气{-w_under + w_over:+.0f}")

    # 4. 裁判
    r_over = row.get("referee_over_bonus", 0) or 0
    r_under = row.get("referee_under_bonus", 0) or 0
    if r_over or r_under:
        score += r_over - r_under
        details.append(f"裁判{-r_under + r_over:+.0f}")

    # 5. 首发
    l_over = row.get("lineup_over_bonus", 0) or 0
    l_under = row.get("lineup_under_bonus", 0) or 0
    if l_over or l_under:
        score += l_over - l_under
        details.append(f"首发{-l_under + l_over:+.0f}")

    score = max(0.0, min(100.0, score))

    if score >= 58:
        direction = "大球"
    elif score <= 42:
        direction = "小球"
    else:
        direction = "观望"

    confidence = round(abs(score - 50) / 50, 2)

    return {
        "score": round(score, 1),
        "direction": direction,
        "confidence": confidence,
        "detail": " | ".join(details),
    }
