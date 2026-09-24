# -*- coding: utf-8 -*-
"""data_source.py - 双数据源（修去重+只取2.5球盘口）"""

import os
import time
import requests
import streamlit as st
from datetime import datetime, timezone

from config import (
    PARSEBOT_API_KEY, PARSEBOT_SCRAPER_ID,
    THEODDS_API_KEY, THEODDS_REGIONS, THEODDS_SPORTS,
)


class NoCreditsError(Exception): pass
class TheOddsKeyError(Exception): pass
class TheOddsQuotaError(Exception): pass


MIN_OVER_ODDS = 1.40
MAX_OVER_ODDS = 8.0
MIN_UNDER_ODDS = 1.40
MAX_UNDER_ODDS = 8.0


def hk_to_euro(hk):
    try:
        v = float(hk) + 1.0
        return round(v, 2) if 1.01 <= v <= 10.0 else None
    except (TypeError, ValueError):
        return None


def parse_line(raw):
    try:
        v = float(raw)
        return round(v, 2) if 1.5 <= v <= 4.5 else None
    except (TypeError, ValueError):
        return None


# ============ Parse.bot ============
_PARSEBOT_BASE = "https://api.parse.bot"


def _parsebot_headers():
    return {"X-API-Key": PARSEBOT_API_KEY, "Accept": "application/json"}


@st.cache_data(ttl=300, show_spinner=False)
def _parsebot_get_live_scores():
    if not PARSEBOT_API_KEY or not PARSEBOT_SCRAPER_ID:
        return [], "Parse.bot 配置缺失"
    url = f"{_PARSEBOT_BASE}/scraper/{PARSEBOT_SCRAPER_ID}/get_live_scores"
    try:
        r = requests.get(url, headers=_parsebot_headers(), timeout=20)
        if r.status_code == 402:
            raise NoCreditsError("Parse.bot 积分不足")
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        return r.json().get("data", {}).get("matches", []), None
    except NoCreditsError:
        raise
    except Exception as e:
        return [], str(e)


@st.cache_data(ttl=300, show_spinner=False)
def _parsebot_get_odds(match_id):
    url = f"{_PARSEBOT_BASE}/scraper/{PARSEBOT_SCRAPER_ID}/get_over_under_odds"
    try:
        r = requests.get(url, headers=_parsebot_headers(),
                         params={"match_id": str(match_id)}, timeout=20)
        if r.status_code == 402:
            d = r.json().get("error", {})
            raise NoCreditsError(f"需 {d.get('required_credits', '?')}，余 {d.get('balance', '?')}")
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"
        return r.json().get("data", {}).get("odds", []), None
    except NoCreditsError:
        raise
    except Exception as e:
        return [], str(e)


def _parsebot_aggregate(odds_list):
    if not odds_list or len(odds_list) < 3:
        return None
    io, iu, il, lo, lu, ll = [], [], [], [], [], []
    for o in odds_list:
        op, cu = o.get("opening", {}), o.get("current", {})
        oe = hk_to_euro(op.get("over"))
        ue = hk_to_euro(op.get("under"))
        ol = parse_line(op.get("total_num"))
        ce = hk_to_euro(cu.get("over"))
        cu_ = hk_to_euro(cu.get("under"))
        cl = parse_line(cu.get("total_num"))
        if oe and ue and ol:
            io.append(oe); iu.append(ue); il.append(ol)
        if ce and cu_ and cl:
            lo.append(ce); lu.append(cu_); ll.append(cl)

    def avg(l):
        return round(sum(l) / len(l), 3) if l else None

    a_io, a_iu, a_il = avg(io), avg(iu), avg(il)
    a_lo, a_lu, a_ll = avg(lo), avg(lu), avg(ll)
    sig = 0.0
    if a_il and a_ll:
        sig += 1.0 * (a_ll - a_il)
    if a_io and a_lo:
        sig -= 1.5 * (a_lo - a_io)
    sig = max(-1.0, min(1.0, sig))
    return {
        "initial_over": a_io, "initial_under": a_iu, "initial_line": a_il,
        "live_over": a_lo, "live_under": a_lu, "live_line": a_ll,
        "sig": round(sig, 3), "companies": len(odds_list),
    }


def fetch_from_parsebot(progress_cb=None):
    matches, err = _parsebot_get_live_scores()
    if err:
        return [], err
    results = []
    for i, m in enumerate(matches):
        mid = m.get("match_id")
        if not mid:
            continue
        if progress_cb:
            progress_cb(i + 1, len(matches), m.get("home_team", "?"))
        try:
            odds, e = _parsebot_get_odds(mid)
        except NoCreditsError:
            raise
        except Exception:
            continue
        if e or not odds:
            continue
        agg = _parsebot_aggregate(odds)
        if not agg:
            continue
        results.append({
            "match_id": mid,
            "league": m.get("league", ""),
            "home": m.get("home_team", ""),
            "away": m.get("away_team", ""),
            "kickoff": m.get("event_date") or m.get("match_time", ""),
            "source": "parsebot",
            "has_trajectory": True,
            **agg,
        })
        time.sleep(0.2)
    return results, None


# ============ TheOdds ============
_THEODDS_BASE = "https://api.the-odds-api.com/v4"


def _theodds_fetch_league(sport_key):
    if not THEODDS_API_KEY:
        return [], "TheOdds Key 未配置"
    url = f"{_THEODDS_BASE}/sports/{sport_key}/odds"
    params = {
        "apiKey": THEODDS_API_KEY,
        "regions": THEODDS_REGIONS,
        "markets": "totals",
        "oddsFormat": "decimal",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
    except requests.exceptions.Timeout:
        return [], "超时"
    except Exception as e:
        return [], str(e)

    if r.status_code == 401:
        try:
            err_code = r.json().get("error_code", "")
        except Exception:
            err_code = ""
        if "INVALID" in err_code:
            raise TheOddsKeyError("TheOdds Key 无效")
        raise TheOddsQuotaError("TheOdds 额度耗尽")
    if r.status_code == 429:
        return [], "速率限制"
    if r.status_code != 200:
        return [], f"HTTP {r.status_code}"

    rem = r.headers.get("x-requests-remaining", "?")
    if rem != "?":
        st.session_state["theodds_remaining"] = rem
    return r.json(), None


def _theodds_extract_totals(event):
    """
    只提取 2.5 球盘口的赔率（排除 1.5/3.5 等异常）
    多公司取平均
    """
    over_list, under_list = [], []

    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market.get("key") != "totals":
                continue
            over = under = point = None
            for o in market.get("outcomes", []):
                name = str(o.get("name", "")).lower()
                price = o.get("price")
                if name == "over":
                    over = price
                    point = o.get("point")
                elif name == "under":
                    under = price

            if over and under and point is not None:
                try:
                    line_f = float(point)
                    # ⭐ 只保留 2.5 球
                    if abs(line_f - 2.5) > 0.01:
                        continue
                    over_f = float(over)
                    under_f = float(under)
                    # 赔率范围检查
                    if not (MIN_OVER_ODDS <= over_f <= MAX_OVER_ODDS):
                        continue
                    if not (MIN_UNDER_ODDS <= under_f <= MAX_UNDER_ODDS):
                        continue
                    # 赔率和检查（正常水位 1.9~2.5）
                    if not (1.85 <= over_f + under_f <= 2.6):
                        continue
                    over_list.append(over_f)
                    under_list.append(under_f)
                except (TypeError, ValueError):
                    continue
                break

    if not over_list:
        return None

    return {
        "live_over": round(sum(over_list) / len(over_list), 3),
        "live_under": round(sum(under_list) / len(under_list), 3),
        "live_line": 2.5,
        "companies": len(over_list),
    }


def fetch_from_theodds():
    all_results = []
    errors = []
    for sport_key in THEODDS_SPORTS:
        try:
            events, err = _theodds_fetch_league(sport_key)
        except TheOddsKeyError:
            raise
        except TheOddsQuotaError:
            raise
        except Exception as e:
            errors.append(f"{sport_key}: {e}")
            continue
        if err:
            errors.append(f"{sport_key}: {err}")
            continue
        for ev in events:
            totals = _theodds_extract_totals(ev)
            if not totals:
                continue
            all_results.append({
                "match_id": ev.get("id", ""),
                "league": sport_key,
                "home": ev.get("home_team", ""),
                "away": ev.get("away_team", ""),
                "kickoff": ev.get("commence_time", ""),
                "source": "theodds",
                "has_trajectory": False,
                "initial_over": None, "initial_under": None, "initial_line": None,
                "live_over": totals["live_over"],
                "live_under": totals["live_under"],
                "live_line": totals["live_line"],
                "sig": 0.0,
                "companies": totals["companies"],
            })
        time.sleep(0.3)
    if errors and not all_results:
        return [], " | ".join(errors[:3])
    return all_results, None


def fetch_odds_auto(source="auto", progress_cb=None):
    if source == "parsebot":
        try:
            r, err = fetch_from_parsebot(progress_cb=progress_cb)
            return r, "parsebot", err
        except NoCreditsError as e:
            return [], "parsebot", f"Parse.bot {e}"
    if source == "theodds":
        try:
            r, err = fetch_from_theodds()
            return r, "theodds", err
        except TheOddsKeyError as e:
            return [], "theodds", f"❌ {e}"
        except TheOddsQuotaError as e:
            return [], "theodds", f"❌ {e}"

    parsebot_err = None
    try:
        r, parsebot_err = fetch_from_parsebot(progress_cb=progress_cb)
        if r:
            return r, "parsebot", None
    except NoCreditsError as e:
        parsebot_err = f"Parse.bot {e}"
    except Exception as e:
        parsebot_err = f"Parse.bot 异常: {e}"

    try:
        r, err = fetch_from_theodds()
        if r:
            return r, "theodds", None
        msg = []
        if parsebot_err:
            msg.append(f"Parse.bot: {parsebot_err}")
        if err:
            msg.append(f"TheOdds: {err}")
        return [], "theodds", " | ".join(msg)
    except TheOddsKeyError as e:
        return [], "theodds", f"Parse.bot 失败 + TheOdds {e}"
    except TheOddsQuotaError as e:
        return [], "theodds", f"Parse.bot 失败 + TheOdds {e}"
