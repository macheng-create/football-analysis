# -*- coding: utf-8 -*-
"""referee_fetcher.py - 裁判数据（兼容旧函数名）"""

import streamlit as st
import requests
import os


BZZOIRO_BASE = "https://sports.bzzoiro.com/api/v2"


def _headers():
    token = os.getenv("BZZOIRO_API_KEY", "")
    return {"Authorization": f"Token {token}"} if token else {}


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


# 兼容旧函数名
def get_referee_stats(referee_id):
    return get_referee(referee_id)


def calc_referee_impact(referee_data):
    if not referee_data:
        return 0, 0, "无数据"

    if isinstance(referee_data, dict):
        if "results" in referee_data and referee_data["results"]:
            ref = referee_data["results"][0]
        else:
            ref = referee_data
    else:
        return 0, 0, "格式异常"

    yellow = ref.get("avg_yellow_per_match")
    red = ref.get("avg_red_per_match")
    matches = ref.get("matches")
    name = ref.get("name", "?")

    over_bonus = 0
    under_bonus = 0
    notes = []

    if matches is not None:
        try:
            if int(matches) < 10:
                return 0, 0, f"{name}(样本少)"
        except (ValueError, TypeError):
            pass

    if yellow is not None:
        try:
            y = float(yellow)
            if y > 4.5:
                under_bonus += 4
                notes.append(f"严格{y:.1f}黄")
            elif y > 4.0:
                under_bonus += 2
                notes.append(f"偏严{y:.1f}黄")
            elif y < 3.0:
                over_bonus += 2
                notes.append(f"宽松{y:.1f}黄")
        except (ValueError, TypeError):
            pass

    if red is not None:
        try:
            rr = float(red)
            if rr > 0.15:
                under_bonus += 3
                notes.append(f"红牌多{rr:.2f}")
        except (ValueError, TypeError):
            pass

    note_str = f"{name}: " + "; ".join(notes) if notes else f"{name}(正常)"
    return over_bonus, under_bonus, note_str
