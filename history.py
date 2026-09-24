# -*- coding: utf-8 -*-
"""history.py - 历史记录（修别名）"""

import json
import os
import math
from datetime import datetime

HISTORY_DIR = "analysis_history"


def _ensure_dir():
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)


def _clean(obj):
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean(v) for v in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


def save_analysis(records, params=None, source="auto"):
    _ensure_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}.json"
    filepath = os.path.join(HISTORY_DIR, filename)

    data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "params": params or {},
        "count": len(records),
        "results": _clean(records),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filename


def list_history():
    _ensure_dir()
    files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]
    files.sort(reverse=True)
    return files


def load_history(filename):
    filepath = os.path.join(HISTORY_DIR, filename)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def delete_history(filename):
    filepath = os.path.join(HISTORY_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


def format_label(filename):
    """新版函数名"""
    data = load_history(filename)
    if not data:
        return filename
    ts = data.get("timestamp", filename)
    count = data.get("count", 0)
    source = data.get("source", "?")
    return f"{ts} | {source} | {count}场"


def format_history_label(filename):
    """兼容旧函数名（auto_scan.py 用）"""
    return format_label(filename)


# ============================================================
# 兼容 auto_scan.py 的旧接口（stats / save_record / load_records）
# ============================================================

def _old_db_path():
    return os.path.join("data", "records.json")


def save_record(record):
    """auto_scan.py 的旧接口：保存单条记录"""
    os.makedirs("data", exist_ok=True)
    db = _old_db_path()
    records = []
    if os.path.exists(db):
        try:
            with open(db, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            records = []
    mid = record.get("match_id")
    if mid:
        records = [r for r in records if str(r.get("match_id")) != str(mid)]
    records.append(record)
    with open(db, "w", encoding="utf-8") as f:
        json.dump(_clean(records), f, ensure_ascii=False, indent=2)
    return True


def load_records(limit=100):
    """auto_scan.py 的旧接口：加载记录"""
    db = _old_db_path()
    if not os.path.exists(db):
        return []
    try:
        with open(db, "r", encoding="utf-8") as f:
            records = json.load(f)
        return records[-limit:] if limit else records
    except Exception:
        return []


def get_unfilled_records():
    """未回填赛果的记录"""
    return [r for r in load_records(limit=0) if not r.get("result")]


def stats():
    """统计"""
    recs = load_records(limit=0)
    total = len(recs)
    filled = sum(1 for r in recs if r.get("result"))
    return {"total": total, "filled": filled, "unfilled": total - filled}
