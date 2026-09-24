# -*- coding: utf-8 -*-
"""bzzoiro_source.py - Bzzoiro 主源（逐场调 odds，修复版）"""

import os
import time
import streamlit as st
import requests
from datetime import datetime, timezone, timedelta


BZZOIRO_BASE = "https://sports.bzzoiro.com/api/v2"


def _headers():
    token = os.getenv("BZZOIRO_API_KEY", "")
    return {"Authorization": f"Token {token}"} if token else {}


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def get_league_map():
    """league_id  league_name 映射"""
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/leagues/",
            headers=_headers(),
            params={"limit": 500},
            timeout=15,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        leagues = data if isinstance(data, list) else data.get("results", [])
        return {l.get("id"): l.get("name", "") for l in leagues if l.get("id")}
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def fetch_events_range(date_from, date_to):
    """获取指定日期范围的比赛"""
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/events/",
            headers=_headers(),
            params={
                "date_from": date_from,
                "date_to": date_to,
                "limit": 200,
            },
            timeout=20,
        )
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        return r.json().get("results", []), None
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=600, show_spinner=False)
def get_event_odds(event_id):
    """单独获取单场赔率"""
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/events/{event_id}/odds/",
            headers=_headers(),
            timeout=10,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def _extract_ou(odds_resp):
    """
    从 odds 接口响应中提取 2.5 球赔率
    结构: {"odds": {"over_25_goals": 1.66, "under_25_goals": 2.11, ...}}
    """
    if not isinstance(odds_resp, dict):
        return None, None
    odds = odds_resp.get("odds") or {}
    if not isinstance(odds, dict):
        return None, None
    over = _to_float(odds.get("over_25_goals"))
    under = _to_float(odds.get("under_25_goals"))
    if over and under and 1.2 <= over <= 10.0 and 1.2 <= under <= 10.0:
        # 隐含概率和检查（合理范围 1.02~1.20）
        total = 1.0 / over + 1.0 / under
        if 1.02 <= total <= 1.25:
            return over, under
    return None, None


def fetch_matches(hours=48, progress_cb=None):
    """
    拉今日+未来N小时比赛（逐场调 odds）
    返回: (results, err)
    """
    if not os.getenv("BZZOIRO_API_KEY"):
        return [], "Bzzoiro Key 未配置"

    now_bj = datetime.now(timezone(timedelta(hours=8)))
    date_from = now_bj.strftime("%Y-%m-%d")
    date_to = (now_bj + timedelta(hours=hours + 12)).strftime("%Y-%m-%d")

    events, err = fetch_events_range(date_from, date_to)
    if err:
        return [], err

    if not events:
        return [], None

    league_map = get_league_map()

    # 过滤：只保留未开始 + 在时间范围内的
    deadline = now_bj + timedelta(hours=hours)
    filtered = []
    for ev in events:
        status = str(ev.get("status", "")).lower()
        if status not in ("notstarted", ""):
            continue
        ed = ev.get("event_date")
        if not ed:
            continue
        try:
            s = ed.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_bj = dt.astimezone(timezone(timedelta(hours=8)))
            if dt_bj <= now_bj or dt_bj > deadline:
                continue
            ev["_kickoff_bj"] = dt_bj
        except Exception:
            continue
        filtered.append(ev)

    if not filtered:
        return [], None

    # 逐场调 odds
    results = []
    total = len(filtered)
    for i, ev in enumerate(filtered):
        if progress_cb:
            progress_cb(i + 1, total, ev.get("home_team", "?"))

        ev_id = ev.get("id")
        if not ev_id:
            continue

        odds_resp = get_event_odds(ev_id)
        over, under = _extract_ou(odds_resp)
        if not over or not under:
            continue

        league_id = ev.get("league_id")
        league_name = league_map.get(league_id, f"联赛{league_id}")

        results.append({
            "match_id": str(ev_id),
            "bzzoiro_id": ev_id,
            "league": league_name,
            "league_name": league_name,
            "home": ev.get("home_team", ""),
            "away": ev.get("away_team", ""),
            "kickoff": ev.get("event_date", ""),
            "source": "bzzoiro",
            "has_trajectory": False,
            "initial_over": None,
            "initial_under": None,
            "initial_line": None,
            "live_over": over,
            "live_under": under,
            "live_line": 2.5,
            "sig": 0.0,
            "companies": 1,
            "ml_over_prob": None,
        })
        time.sleep(0.15)

    return results, None
