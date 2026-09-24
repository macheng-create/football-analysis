# daily_scan_task.py
"""每日自动扫描 —— 综合评分版"""

import os
import json
import time
from datetime import datetime
import requests

API_KEY = "pmx_f5199c275477e47eb661978af56c4674"
SCRAPER_ID = "69a47c61-f9da-4d24-b9d0-d490df5a89c1"
BASE_URL = f"https://api.parse.bot/scraper/{SCRAPER_ID}"
HEADERS = {"X-API-Key": API_KEY}

FOCUS_LEAGUES = ["日皇杯", "美职业", "国际友谊", "英超", "西甲", "意甲", "德甲", "法甲"]
ALERT_DIR = "daily_alerts"
MIN_SCORE_DIFF = 15  # 综合评分偏离 50 分的阈值


def fetch_matches():
    r = requests.get(f"{BASE_URL}/get_live_scores", headers=HEADERS, timeout=30)
    return r.json().get("data", {}).get("matches", []) if r.status_code == 200 else []


def fetch_odds(match_id):
    r = requests.get(f"{BASE_URL}/get_over_under_odds", headers=HEADERS,
                     params={"match_id": match_id}, timeout=30)
    return r.json().get("data", {}).get("odds", []) if r.status_code == 200 else []


def hk_to_euro(hk):
    try:
        v = float(hk) + 1.0
        return v if 1.01 <= v <= 10.0 else None
    except Exception:
        return None


def calc_signal(odds_list):
    opens, currents = [], []
    for o in odds_list:
        op = o.get("opening", {})
        cu = o.get("current", {})
        try:
            if op.get("over") is not None and cu.get("over") is not None:
                oe = hk_to_euro(op["over"])
                ce = hk_to_euro(cu["over"])
                ol = float(op.get("total_num", ""))
                cl = float(cu.get("total_num", ""))
                if oe and ce and 1.5 <= ol <= 4.5 and 1.5 <= cl <= 4.5:
                    opens.append((oe, ol))
                    currents.append((ce, cl))
        except Exception:
            continue
    if not opens or not currents:
        return None
    avg_oo = sum(o[0] for o in opens) / len(opens)
    avg_ol = sum(o[1] for o in opens) / len(opens)
    avg_co = sum(c[0] for c in currents) / len(currents)
    avg_cl = sum(c[1] for c in currents) / len(currents)
    sig = 1.0 * (avg_cl - avg_ol) - 1.5 * (avg_co - avg_oo)
    return max(-1.0, min(1.0, sig))


def main():
    print(f"[{datetime.now()}] 开始每日扫描...")
    matches = fetch_matches()
    print(f"共 {len(matches)} 场比赛")

    candidates = [
        m for m in matches
        if m.get("league") in FOCUS_LEAGUES
        and str(m.get("status", "")) in ("0", "1")
    ]
    print(f"筛选后 {len(candidates)} 场候选")

    alerts = []
    for m in candidates:
        mid = m.get("match_id")
        odds = fetch_odds(mid)
        if not odds:
            continue
        sig = calc_signal(odds)
        if sig is None:
            continue
        # 简化的综合评分（只用盘口信号）
        composite = 50 + sig * 50
        if abs(composite - 50) >= MIN_SCORE_DIFF:
            alerts.append({
                "联赛": m.get("league", ""),
                "主队": m.get("home_team", ""),
                "客队": m.get("away_team", ""),
                "开赛时间": m.get("match_time", ""),
                "信号": round(sig, 3),
                "综合评分": round(composite, 1),
                "推荐": "大球" if composite > 50 else "小球",
            })
        time.sleep(0.3)

    os.makedirs(ALERT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(ALERT_DIR, f"{ts}.json")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_candidates": len(candidates),
            "alerts_count": len(alerts),
            "alerts": alerts,
        }, f, ensure_ascii=False, indent=2)

    print(f"[{datetime.now()}] 扫描完成，强信号 {len(alerts)} 场")


if __name__ == "__main__":
    main()