# -*- coding: utf-8 -*-
"""竞彩白名单 + 时间转换"""

from datetime import datetime, timedelta

# ============================================================
# 中国竞彩可投注联赛白名单
# 来源：2025年体彩竞猜赛事范围
# ============================================================
CN_LOTTERY_LEAGUES = [
    # 欧洲五大联赛
    "英超", "英冠", "西甲", "西乙", "德甲", "德乙",
    "意甲", "意乙", "法甲", "法乙",
    # 欧洲杯赛
    "欧洲冠军联赛", "欧罗巴联赛", "欧洲协会联赛",
    # 亚洲赛事
    "亚冠精英", "亚冠联赛", "亚洲杯", "亚运男足", "亚运女足",
    "J1联赛", "J2联赛", "日本天皇杯",
    "K联赛1", "韩足总杯",
    "中超", "中甲",
    # 美洲赛事
    "巴西甲级联赛", "巴甲", "阿根廷甲级联赛", "解放者杯",
    "美国大联盟", "MLS",
    # 其他欧洲
    "荷甲", "葡超", "比甲", "土超",
    "苏超", "瑞士超", "奥地利甲级联赛",
    "丹超", "挪超", "瑞超", "芬超", "俄超",
    # 国际赛事
    "世界杯预选赛", "世预赛(亚洲)", "世预赛(欧洲)",
    "世预赛(南美)", "世预赛(中北美)", "世预赛(非洲)",
    "国际友谊赛", "俱乐部友谊赛",
    "国际足联俱乐部世界杯", "U20世青赛",
    "中北美国家联赛",
]


def is_lottery_league(league_cn):
    """判断联赛是否在竞彩白名单内"""
    if not league_cn:
        return False
    for l in CN_LOTTERY_LEAGUES:
        if l in league_cn or league_cn in l:
            return True
    return False


def utc_to_beijing(utc_str):
    """UTC 时间字符串 → 北京时间字符串"""
    if not utc_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        dt_bj = dt + timedelta(hours=8)
        return dt_bj.strftime("%m-%d %H:%M")
    except Exception:
        return utc_str[:16].replace("T", " ")


def beijing_to_utc_date_range(days_ahead=0):
    """返回北京时间的今天起 N 天的 UTC 日期范围"""
    now_bj = datetime.utcnow() + timedelta(hours=8)
    target_bj = now_bj + timedelta(days=days_ahead)
    start_utc = (target_bj - timedelta(hours=8)).strftime("%Y-%m-%d")
    end_utc = (target_bj - timedelta(hours=8)).strftime("%Y-%m-%d")
    return start_utc, end_utc