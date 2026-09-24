# -*- coding: utf-8 -*-
"""odds_history.py - 赔率变化追踪（每次刷新都记录快照）"""

import json
import os
from datetime import datetime


FILE = "odds_history.json"


def _load():
    if not os.path.exists(FILE):
        return {}
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _match_key(home, away):
    """用主客队名做 key"""
    return f"{home}|{away}"


def record_snapshot(results):
    """
    记录一次赔率快照
    每个 match 保留最近 50 条记录
    """
    data = _load()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for r in results:
        home = r.get("home", "")
        away = r.get("away", "")
        if not home or not away:
            continue

        key = _match_key(home, away)
        if key not in data:
            data[key] = {
                "home": home,
                "away": away,
                "league": r.get("league", ""),
                "kickoff": r.get("kickoff", ""),
                "snapshots": [],
            }

        snap = {
            "ts": ts,
            "over": r.get("live_over"),
            "under": r.get("live_under"),
            "line": r.get("live_line"),
            "source": r.get("source", ""),
        }
        # 避免重复（同一分钟内不重复记录相同值）
        snaps = data[key]["snapshots"]
        if snaps:
            last = snaps[-1]
            if (last.get("over") == snap["over"]
                    and last.get("under") == snap["under"]
                    and last.get("line") == snap["line"]):
                continue
        snaps.append(snap)
        # 只保留最近 50 条
        data[key]["snapshots"] = snaps[-50:]

    _save(data)


def get_snapshots(home, away):
    """获取某场比赛的所有快照"""
    data = _load()
    key = _match_key(home, away)
    return data.get(key, {}).get("snapshots", [])


def analyze_movement(home, away):
    """
    分析赔率变化
    返回: {
        "first": {...},
        "last": {...},
        "over_change": -0.25,   # 负数=大球赔率降
        "under_change": +0.15,  # 正数=小球赔率升
        "line_change": 0.0,
        "movement_signal": +0.5,  # 正=看好大球
        "note": "大球赔率降0.25，庄家看好大球",
        "snapshots_count": 5
    }
    """
    snaps = get_snapshots(home, away)
    if len(snaps) < 2:
        return None

    first = snaps[0]
    last = snaps[-1]

    try:
        oc = float(last["over"]) - float(first["over"])
        uc = float(last["under"]) - float(first["under"])
        lc = (float(last["line"]) - float(first["line"])
              if last.get("line") and first.get("line") else 0)
    except (ValueError, TypeError):
        return None

    # 信号计算（与盘口轨迹类似）
    sig = 1.0 * lc - 1.5 * oc

    notes = []
    if oc < -0.10:
        notes.append(f"大球赔率降{abs(oc):.2f}")
    elif oc > 0.10:
        notes.append(f"大球赔率升{oc:.2f}")

    if uc < -0.10:
        notes.append(f"小球赔率降{abs(uc):.2f}")
    elif uc > 0.10:
        notes.append(f"小球赔率升{uc:.2f}")

    if abs(lc) > 0.20:
        if lc > 0:
            notes.append(f"盘口升{lc:.2f}")
        else:
            notes.append(f"盘口降{abs(lc):.2f}")

    note = " / ".join(notes) if notes else "无明显变化"

    return {
        "first": first,
        "last": last,
        "over_change": round(oc, 3),
        "under_change": round(uc, 3),
        "line_change": round(lc, 3),
        "movement_signal": round(max(-1.0, min(1.0, sig)), 3),
        "note": note,
        "snapshots_count": len(snaps),
    }


def clear_history():
    """清空所有历史"""
    if os.path.exists(FILE):
        os.remove(FILE)
    return True
