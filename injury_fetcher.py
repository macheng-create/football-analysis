# -*- coding: utf-8 -*-
"""injury_fetcher.py - 伤停数据（兼容旧函数名）"""

import streamlit as st
import requests
import os


BZZOIRO_BASE = "https://sports.bzzoiro.com/api/v2"


def _headers():
    token = os.getenv("BZZOIRO_API_KEY", "")
    return {"Authorization": f"Token {token}"} if token else {}


@st.cache_data(ttl=1800, show_spinner=False)
def get_squad(team_id):
    """获取球队阵容"""
    try:
        r = requests.get(
            f"{BZZOIRO_BASE}/teams/{team_id}/squad/",
            headers=_headers(), timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("results", [])
    except Exception:
        return []


# 兼容旧函数名
def get_squad_availability(team_id):
    return get_squad(team_id)


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


def calc_injury_impact(squad):
    """伤停影响评分"""
    if not squad:
        return 0, 0, "无数据"

    injured = []
    suspended = []
    doubtful = []

    for p in squad:
        if not isinstance(p, dict):
            continue
        avail = (
            p.get("availability")
            or p.get("status")
            or p.get("condition")
            or ""
        ).lower()

        if not avail or avail == "available":
            if p.get("is_injured"):
                avail = "injured"
            elif p.get("is_suspended"):
                avail = "suspended"
            else:
                continue

        name = p.get("name") or p.get("player_name") or "?"
        pos = (p.get("position") or p.get("pos") or "").upper()

        if "injur" in avail:
            injured.append((name, pos))
        elif "suspend" in avail:
            suspended.append((name, pos))
        elif "doubt" in avail:
            doubtful.append((name, pos))

    total_missing = len(injured) + len(suspended)

    over_bonus = 0
    under_bonus = 0
    notes = []

    if total_missing >= 5:
        under_bonus += 5
        notes.append(f"缺{total_missing}人")
    elif total_missing >= 3:
        under_bonus += 3
        notes.append(f"缺{total_missing}人")

    if len(doubtful) >= 3:
        under_bonus += 2
        notes.append(f"疑{len(doubtful)}人")

    for name, pos in injured + suspended:
        if pos in ("F", "FW", "ST", "CF", "前锋"):
            under_bonus += 3
            notes.append(f"{name}(前锋)")
        elif pos in ("D", "DF", "CB", "后卫"):
            over_bonus += 2
            notes.append(f"{name}(后卫)")

    note_str = "; ".join(notes) if notes else "完整"
    return over_bonus, under_bonus, note_str
