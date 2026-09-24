# -*- coding: utf-8 -*-
"""config.py - 双数据源配置（修复 Key 读取）"""

import os
from dotenv import load_dotenv

# 强制指定 .env 绝对路径 + 覆盖已有环境变量
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)

# Parse.bot
PARSEBOT_API_KEY = os.getenv("PARSEBOT_API_KEY", "").strip()
PARSEBOT_SCRAPER_ID = os.getenv("PARSEBOT_SCRAPER_ID", "").strip()

# TheOdds
THEODDS_API_KEY = os.getenv("THEODDS_API_KEY", "").strip()
THEODDS_REGIONS = os.getenv("THEODDS_REGIONS", "eu").strip()

_raw_sports = os.getenv(
    "AUTO_LEAGUES",
    "soccer_epl,soccer_spain_la_liga,soccer_italy_serie_a,"
    "soccer_germany_bundesliga,soccer_france_ligue_one,soccer_uefa_champs_league"
)
THEODDS_SPORTS = [s.strip() for s in _raw_sports.split(",") if s.strip()]

DEFAULT_SOURCE = os.getenv("DEFAULT_SOURCE", "auto").strip()


def validate_config():
    """启动时自检，返回问题列表"""
    problems = []
    if not PARSEBOT_API_KEY:
        problems.append("PARSEBOT_API_KEY 未配置")
    if not PARSEBOT_SCRAPER_ID:
        problems.append("PARSEBOT_SCRAPER_ID 未配置")
    if not THEODDS_API_KEY:
        problems.append("THEODDS_API_KEY 未配置")
    elif len(THEODDS_API_KEY) != 32:
        problems.append(f"THEODDS_API_KEY 长度异常（{len(THEODDS_API_KEY)}，应为 32）")
    if not THEODDS_SPORTS:
        problems.append("AUTO_LEAGUES 为空")
    return problems


if __name__ == "__main__":
    print("=== 配置自检 ===")
    print(f"PARSEBOT_API_KEY: {PARSEBOT_API_KEY[:15]}..." if PARSEBOT_API_KEY else "PARSEBOT_API_KEY: 未配置")
    print(f"THEODDS_API_KEY:  {THEODDS_API_KEY[:15]}..." if THEODDS_API_KEY else "THEODDS_API_KEY: 未配置")
    print(f"THEODDS_KEY_LEN:  {len(THEODDS_API_KEY)}")
    print(f"SPORTS: {THEODDS_SPORTS}")
    print(f"SOURCE: {DEFAULT_SOURCE}")
    issues = validate_config()
    if issues:
        print("\n❌ 问题：")
        for i in issues:
            print(f"  - {i}")
    else:
        print("\n✅ 配置完整")