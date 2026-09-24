# -*- coding: utf-8 -*-
"""report.py - 生成 Markdown 报告（动态说明 v2）"""

import os
from datetime import datetime, timezone, timedelta
from translate import cn_league, cn_team

REPORT_DIR = "reports"


def _ensure_dir():
    if not os.path.exists(REPORT_DIR):
        os.makedirs(REPORT_DIR)


def _format_kickoff(kickoff):
    if not kickoff:
        return ""
    try:
        if "T" in kickoff:
            s = kickoff.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_bj = dt.astimezone(timezone(timedelta(hours=8)))
            return dt_bj.strftime("%m-%d %H:%M")
    except Exception:
        pass
    return kickoff.replace("T", " ")[:16]


def _suggest_odds(score, direction):
    if direction == "大球":
        p = score / 100.0
    elif direction == "小球":
        p = (100 - score) / 100.0
    else:
        return ""
    if p <= 0 or p >= 1:
        return ""
    fair = 1.0 / p
    threshold = round(fair * 1.05, 2)
    return f"{threshold}"


def _source_desc(source):
    desc = {
        "bzzoiro": "Bzzoiro Sports（免费） 含赛前赔率",
        "theodds": "TheOdds API（免费） 含赔率",
        "sporttery": "中国竞彩官网（免费） 含官方赔率",
        "parsebot": "Parse.bot（球探网） 含盘口轨迹",
        "all": "全部整合（Bzzoiro + TheOdds + 竞彩）",
        "both": "TheOdds + 竞彩",
    }
    if source.startswith("临场检测"):
        return source
    return desc.get(source, source)


def _score_desc(source):
    if source in ("bzzoiro", "all"):
        return "评分 = 赔率隐含概率（基础）+ 赔率变化 + 天气 + 裁判 + 伤停"
    elif source == "parsebot":
        return "评分 = 盘口轨迹（60%权重）+ 赔率变化 + 天气 + 裁判 + 伤停"
    else:
        return "评分 = 市场隐含概率  100"


def generate_report(results, source="auto", params=None):
    _ensure_dir()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"report_{ts}.md"
    filepath = os.path.join(REPORT_DIR, filename)

    lines = []
    lines.append("# ⚽ 足球大小球分析报告")
    lines.append("")
    lines.append(f"**生成时间(北京)**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**数据源**：{_source_desc(source)}")
    lines.append(f"**总场次**：{len(results)} 场")
    if params:
        lines.append(f"**参数**：{params}")
    lines.append("")

    df_over = [r for r in results if r.get("direction") == "大球"]
    df_under = [r for r in results if r.get("direction") == "小球"]
    df_wait = [r for r in results if r.get("direction") == "观望"]
    df_ml = [r for r in results if r.get("ml_over_prob")]

    lines.append("## 一、概览")
    lines.append("")
    lines.append(f"- 推荐大球：**{len(df_over)}** 场")
    lines.append(f"- 推荐小球：**{len(df_under)}** 场")
    lines.append(f"- 观望：**{len(df_wait)}** 场")
    if df_ml:
        lines.append(f"- 含ML预测：**{len(df_ml)}** 场")
    lines.append("")

    lines.append("## 二、评分说明")
    lines.append("")
    lines.append(f"- **评分逻辑**：{_score_desc(source)}")
    lines.append("- **开云建议赔率**：公平赔率  1.05，开云赔率  此值才有正期望")
    lines.append("- **下注前必须**：打开开云 App 核对实时赔率")
    lines.append("- **数据延迟提示**：Bzzoiro 有延迟，滚球决策以开云 App 为准")
    lines.append("")

    df_bet = df_over + df_under

    if df_bet:
        lines.append("## 三、推荐场次（按评分排序）")
        lines.append("")
        lines.append("| 联赛 | 主队 | 客队 | 开赛时间 | 盘口 | 大球赔率 | 小球赔率 | ML预测 | 评分 | 推荐 | 开云建议 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

        sorted_bets = sorted(df_bet, key=lambda x: -abs((x.get("score") or 50) - 50))
        for r in sorted_bets:
            score = r.get("score", 50)
            direction = r.get("direction", "")
            suggest = _suggest_odds(score, direction)
            ml = r.get("ml_over_prob")
            ml_str = f"{ml * 100:.1f}%" if ml else ""

            lines.append(
                f"| {cn_league(r.get('league_name', '') or r.get('league', ''))} "
                f"| {cn_team(r.get('home', ''))} "
                f"| {cn_team(r.get('away', ''))} "
                f"| {_format_kickoff(r.get('kickoff', ''))} "
                f"| {r.get('live_line', '')} "
                f"| {r.get('live_over', '')} "
                f"| {r.get('live_under', '')} "
                f"| {ml_str} "
                f"| {score} "
                f"| {direction} "
                f"| {suggest} |"
            )
        lines.append("")

    lines.append("## 四、全部场次")
    lines.append("")
    lines.append("| 联赛 | 主队 | 客队 | 开赛时间 | 大球赔率 | 小球赔率 | 盘口 | ML预测 | 评分 | 推荐 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda x: -(x.get("score") or 50)):
        ml = r.get("ml_over_prob")
        ml_str = f"{ml * 100:.1f}%" if ml else ""
        lines.append(
            f"| {cn_league(r.get('league_name', '') or r.get('league', ''))} "
            f"| {cn_team(r.get('home', ''))} "
            f"| {cn_team(r.get('away', ''))} "
            f"| {_format_kickoff(r.get('kickoff', ''))} "
            f"| {r.get('live_over', '')} "
            f"| {r.get('live_under', '')} "
            f"| {r.get('live_line', '')} "
            f"| {ml_str} "
            f"| {r.get('score', '')} "
            f"| {r.get('direction', '')} |"
        )
    lines.append("")

    lines.append("## 五、请帮我分析")
    lines.append("")
    lines.append("1. 推荐场次中哪些最可信？")
    lines.append("2. 仓位建议（假设总资金 10000 元）")
    lines.append("3. 开云 App 上的实际赔率是否达到'建议赔率'？")
    lines.append("")

    content = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return content
