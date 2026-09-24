# -*- coding: utf-8 -*-
"""manual_odds.py - 手动开云赔率数据管理（支持多次填写）"""

import json
import os
from datetime import datetime

MANUAL_FILE = "manual_odds.json"


def _load():
    if not os.path.exists(MANUAL_FILE):
        return {}
    try:
        with open(MANUAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    with open(MANUAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_record(match_id, match_name, line, over, under, note=""):
    """添加一条开云数据记录"""
    data = _load()
    if match_id not in data:
        data[match_id] = {
            "match_name": match_name,
            "records": [],
        }
    data[match_id]["records"].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "line": float(line) if line else None,
        "over": float(over) if over else None,
        "under": float(under) if under else None,
        "note": note,
    })
    _save(data)
    return True


def get_records(match_id):
    data = _load()
    return data.get(match_id, {}).get("records", [])


def get_all():
    return _load()


def delete_record(match_id, index):
    data = _load()
    if match_id in data and 0 <= index < len(data[match_id]["records"]):
        del data[match_id]["records"][index]
        _save(data)
        return True
    return False


def delete_match(match_id):
    data = _load()
    if match_id in data:
        del data[match_id]
        _save(data)
        return True
    return False


def compare_with_advice(records, advice_odds, direction):
    """
    对比开云记录和建议赔率
    返回: (是否值得下注, 说明)
    """
    if not records or advice_odds is None:
        return None, "无数据"

    # 取最新记录
    latest = records[-1]
    if direction == "大球":
        actual = latest.get("over")
    elif direction == "小球":
        actual = latest.get("under")
    else:
        return None, "无方向"

    if actual is None:
        return None, "未填赔率"

    try:
        advice = float(advice_odds)
    except (ValueError, TypeError):
        return None, "建议赔率无效"

    if actual >= advice:
        return True, f"✅ 值得下注（开云 {actual}  建议 {advice}）"
    else:
        return False, f"❌ 跳过（开云 {actual} < 建议 {advice}）"
