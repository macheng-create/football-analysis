# -*- coding: utf-8 -*-
"""sporttery_fetcher.py - 中国竞彩官网数据抓取"""

import requests
from datetime import date, datetime, timezone, timedelta


SPORTTERY_URL = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry"


def fetch_sporttery_matches(match_date=None):
    """获取竞彩当天可投注比赛 + 总进球赔率"""
    try:
        if not match_date:
            match_date = date.today().strftime("%Y-%m-%d")

        params = {
            "channel": "c",
            "poolCode": "hhad,had,ttg,hafu",
            "matchBeginDate": match_date,
            "matchEndDate": match_date,
            "pageSize": 100,
            "pageNo": 1,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36",
            "Referer": "https://www.sporttery.cn/",
        }
        r = requests.get(SPORTTERY_URL, params=params, headers=headers, timeout=15)
        if r.status_code != 200:
            return [], f"HTTP {r.status_code}"

        data = r.json()
        if not data.get("success"):
            return [], data.get("errorMessage", "接口返回失败")

        results = []
        for day in data.get("value", {}).get("matchInfoList", []):
            for m in day.get("subMatchList", []):
                match_time_bj = (
                    m.get("matchDate", "") + " " + m.get("matchTime", "")
                )[:16]

                # 解析总进球赔率
                ttg = m.get("ttg", {})
                over_odds, under_odds = _parse_ttg(ttg)

                # 竞彩场次号
                match_num = m.get("matchNumStr", "")

                results.append({
                    "match_id": f"sp_{m.get('matchId', '')}",
                    "league": m.get("leagueAbbName", ""),
                    "home": m.get("homeTeamAbbName", ""),
                    "away": m.get("awayTeamAbbName", ""),
                    "kickoff": match_time_bj,  # 竞彩本身就是北京时间
                    "source": "sporttery",
                    "has_trajectory": False,
                    "initial_over": None,
                    "initial_under": None,
                    "initial_line": None,
                    "live_over": over_odds,
                    "live_under": under_odds,
                    "live_line": 2.5,  # 竞彩固定用 2.5 反推
                    "sig": 0.0,
                    "companies": 1,
                    "match_num": match_num,
                })
        return results, None
    except Exception as e:
        return [], str(e)


def _parse_ttg(ttg):
    """总进球赔率反推大小球 2.5"""
    if not ttg:
        return None, None

    try:
        odds = {}
        for i in range(8):
            key = f"s{i}"
            v = ttg.get(key)
            if v is None:
                return None, None
            odds[i] = float(v)
    except (ValueError, TypeError):
        return None, None

    # 反隐含概率
    raw = {k: 1.0 / v for k, v in odds.items() if v > 1.0}
    total = sum(raw.values())
    if total <= 0:
        return None, None
    probs = {k: p / total for k, p in raw.items()}

    # 大2.5 = s3+s4+s5+s6+s7；小2.5 = s0+s1+s2
    p_under = sum(probs.get(k, 0) for k in [0, 1, 2])
    p_over = 1 - p_under

    if p_over <= 0 or p_under <= 0:
        return None, None

    # 竞彩返奖率约 80%，实际赔率 = 公平赔率  0.8
    over_odds = round(1.0 / p_over * 0.8, 2)
    under_odds = round(1.0 / p_under * 0.8, 2)

    # ⭐ 合理性过滤：竞彩反推的大球赔率正常在 1.5~3.0 之间
    # 低于 1.5 说明反推算法出错，直接丢弃
    if not (1.50 <= over_odds <= 3.0):
        return None, None
    if not (1.50 <= under_odds <= 3.0):
        return None, None

    return over_odds, under_odds
