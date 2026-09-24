# -*- coding: utf-8 -*-
"""bzzoiro_enricher.py - 用队名+日期匹配Bzzoiro，获取裁判+首发"""

import os
import re
import streamlit as st
import requests
from datetime import datetime, timedelta, timezone


BZZOIRO_BASE = "https://sports.bzzoiro.com/api/v2"


def _headers():
    token = os.getenv("BZZOIRO_API_KEY", "")
    return {"Authorization": f"Token {token}"} if token else {}


def _normalize(name):
    """归一化队名（去FC/CF/空格/符号）"""
    if not name:
        return ""
    n = str(name).lower()
    n = re.sub(r"\b(fc|cf|sc|ac|afc|as|ss|ssc|club|football|soccer|team|utd|united)\b", " ", n)
    n = re.sub(r"[\s\-\.&'()]", "", n)
    return n


@st.cache_data(ttl=1800, show_spinner=False)
def find_event_id(home, away, kickoff_iso):
    """用队名+日期在 Bzzoiro 找 event_id"""
    if not kickoff_iso:
        return None
    try:
        s = kickoff_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        date_before = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
        date_after = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return None

    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/events/",
            headers=_headers(),
            params={"date_from": date_before, "date_to": date_after, "limit": 100},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        events = r.json().get("results", [])
    except Exception:
        return None

    home_norm = _normalize(home)
    away_norm = _normalize(away)
    if not home_norm or not away_norm:
        return None

    for ev in events:
        h = _normalize(ev.get("home_team", ""))
        a = _normalize(ev.get("away_team", ""))
        if (h and (home_norm in h or h in home_norm) and
            a and (away_norm in a or a in away_norm)):
            return ev.get("id")
    return None


@st.cache_data(ttl=1800, show_spinner=False)
def get_event_detail(event_id):
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/events/{event_id}/",
            headers=_headers(), timeout=15,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_referee(referee_id):
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/referees/{referee_id}/",
            headers=_headers(), timeout=15,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def calc_referee_impact(ref_data):
    """裁判风格  大小球加分"""
    if not ref_data:
        return 0, 0, "无"

    if isinstance(ref_data, dict) and "results" in ref_data and ref_data["results"]:
        ref = ref_data["results"][0]
    else:
        ref = ref_data
    if not isinstance(ref, dict):
        return 0, 0, "无"

    yellow = ref.get("avg_yellow_per_match")
    red = ref.get("avg_red_per_match")
    matches = ref.get("matches")
    name = ref.get("name", "?")

    if matches is not None:
        try:
            if int(matches) < 10:
                return 0, 0, f"{name}(少样本)"
        except (ValueError, TypeError):
            pass

    over_bonus = 0
    under_bonus = 0
    notes = []

    if yellow is not None:
        try:
            y = float(yellow)
            if y > 4.5:
                under_bonus += 4; notes.append(f"严{y:.1f}")
            elif y > 4.0:
                under_bonus += 2; notes.append(f"偏严{y:.1f}")
            elif y < 3.0:
                over_bonus += 2; notes.append(f"松{y:.1f}")
        except (ValueError, TypeError):
            pass

    if red is not None:
        try:
            if float(red) > 0.15:
                under_bonus += 3; notes.append("红多")
        except (ValueError, TypeError):
            pass

    if not notes:
        return 0, 0, f"{name}(正常)"
    return over_bonus, under_bonus, f"{name}:{'+'.join(notes)}"


def _find_lineup(detail, side):
    """从 detail 里找首发名单（尝试多种字段名）"""
    if not detail:
        return []
    for key in [f"{side}_lineup", f"{side}_xi", f"{side}_players",
                f"{side}_starters", f"{side}Lineup"]:
        v = detail.get(key)
        if isinstance(v, list) and v:
            return v
    return []


def enrich_match(match):
    """对单场比赛富化裁判+首发"""
    home = match.get("home", "")
    away = match.get("away", "")
    kickoff = match.get("kickoff", "")

    if not os.getenv("BZZOIRO_API_KEY"):
        match["referee_note"] = "无Key"
        match["lineup_note"] = "无Key"
        match["referee_over_bonus"] = 0
        match["referee_under_bonus"] = 0
        match["lineup_over_bonus"] = 0
        match["lineup_under_bonus"] = 0
        return match

    ev_id = find_event_id(home, away, kickoff)
    if not ev_id:
        match["referee_note"] = "未匹配"
        match["lineup_note"] = "未匹配"
        match["referee_over_bonus"] = 0
        match["referee_under_bonus"] = 0
        match["lineup_over_bonus"] = 0
        match["lineup_under_bonus"] = 0
        return match

    match["bzzoiro_event_id"] = ev_id

    detail = get_event_detail(ev_id) or {}

    # 裁判
    ref_id = detail.get("referee_id")
    if ref_id:
        ref_data = get_referee(ref_id)
        o, u, note = calc_referee_impact(ref_data)
        match["referee_over_bonus"] = o
        match["referee_under_bonus"] = u
        match["referee_note"] = note
    else:
        match["referee_over_bonus"] = 0
        match["referee_under_bonus"] = 0
        match["referee_note"] = "未指定"

    # 首发
    home_xi = _find_lineup(detail, "home")
    away_xi = _find_lineup(detail, "away")

    if home_xi or away_xi:
        match["lineup_note"] = f"主{len(home_xi)}/客{len(away_xi)}"
        match["lineup_over_bonus"] = 0
        match["lineup_under_bonus"] = 0
    else:
        match["lineup_note"] = "未公布"
        match["lineup_over_bonus"] = 0
        match["lineup_under_bonus"] = 0

    return match


def enrich_batch(matches, max_count=20):
    """批量富化（只处理前 N 场，避免太慢）"""
    for i, m in enumerate(matches):
        if i >= max_count:
            m.setdefault("referee_note", "跳过")
            m.setdefault("lineup_note", "跳过")
            m.setdefault("referee_over_bonus", 0)
            m.setdefault("referee_under_bonus", 0)
            m.setdefault("lineup_over_bonus", 0)
            m.setdefault("lineup_under_bonus", 0)
            continue
        try:
            enrich_match(m)
        except Exception:
            m.setdefault("referee_note", "异常")
            m.setdefault("lineup_note", "异常")
    return matches
