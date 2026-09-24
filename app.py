# -*- coding: utf-8 -*-
"""app.py - v32（Bzzoiro主源完整版）"""

import streamlit as st
st.markdown(r"""<style>.stDeployButton {display:none;}</style>""", unsafe_allow_html=True)
import pandas as pd
import os
import re
from datetime import datetime, timezone, timedelta

from config import validate_config, THEODDS_API_KEY, PARSEBOT_API_KEY
from data_source import (
    fetch_from_theodds, fetch_odds_auto,
    NoCreditsError, TheOddsKeyError, TheOddsQuotaError,
)
from bzzoiro_source import fetch_matches as fetch_bzzoiro_matches
from sporttery_fetcher import fetch_sporttery_matches
from rating import calc_rating
from report import generate_report, _suggest_odds
from translate import cn_league, cn_team
from weather_fetcher import enrich_with_weather
from bzzoiro_enricher import enrich_batch
from odds_history import (
    record_snapshot, analyze_movement, clear_history,
)
from manual_odds import (
    add_record, get_records, get_all,
    delete_match, compare_with_advice,
)
from history import (
    save_analysis, list_history, load_history,
    delete_history, format_label,
)

st.set_page_config(page_title="足球大小球分析系统", layout="wide")
st.title("⚽ 足球大小球赔率分析系统 v32")


def _parse_kickoff(kickoff):
    if not kickoff:
        return None
    try:
        if "T" in kickoff:
            s = kickoff.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone(timedelta(hours=8)))
        else:
            return datetime.fromisoformat(kickoff).replace(
                tzinfo=timezone(timedelta(hours=8)))
    except Exception:
        return None


def _format_kickoff(kickoff):
    dt = _parse_kickoff(kickoff)
    return dt.strftime("%m-%d %H:%M") if dt else (
        kickoff.replace("T", " ")[:16] if kickoff else "")


def _countdown(kickoff):
    dt = _parse_kickoff(kickoff)
    if not dt:
        return ""
    now = datetime.now(timezone(timedelta(hours=8)))
    secs = int((dt - now).total_seconds())
    if secs < 0:
        return "进行中" if secs > -7200 else "已结束"
    h = secs // 3600
    m = (secs % 3600) // 60
    return f"{h // 24}天{h % 24}小时" if h >= 24 else (
        f"{h}小时{m}分" if h > 0 else f"{m}分钟")


def _normalize_name(name):
    if not name:
        return ""
    n = cn_team(name)
    return re.sub(r"[\s\-\.&]", "", str(n).lower())


def _deduplicate(results):
    priority = {"bzzoiro": 4, "sporttery": 3, "theodds": 2, "parsebot": 1}
    seen = {}
    for r in results:
        key = (_normalize_name(r.get("home", "")),
               _normalize_name(r.get("away", "")))
        if not key[0] or not key[1]:
            continue
        if key not in seen:
            seen[key] = r
        else:
            cur_p = priority.get(r.get("source"), 0)
            old_p = priority.get(seen[key].get("source"), 0)
            if cur_p > old_p:
                seen[key] = r
    return list(seen.values())


def _filter_by_hours(results, hours):
    if hours <= 0:
        return results
    now = datetime.now(timezone(timedelta(hours=8)))
    deadline = now + timedelta(hours=hours)
    out = []
    for r in results:
        dt = _parse_kickoff(r.get("kickoff"))
        if dt and now < dt <= deadline:
            out.append(r)
    return out


# 启动自检
issues = validate_config()
if issues:
    with st.expander("⚠️ 配置检查", expanded=True):
        for i in issues:
            st.warning(i)

# 侧边栏
with st.sidebar:
    st.header("⚙️ 数据源")
    source_mode = st.radio(
        "选择数据源",
        ["Bzzoiro（主源）", "TheOdds", "竞彩官网", "全部整合"],
        index=0,
    )
    source_map = {
        "Bzzoiro（主源）": "bzzoiro",
        "TheOdds": "theodds",
        "竞彩官网": "sporttery",
        "全部整合": "all",
    }
    source = source_map[source_mode]

    st.divider()
    st.header("⏰ 时间过滤")
    hours = st.slider("未来 N 小时内", 12, 720, 48, 12)

    st.divider()
    st.header("📊 增强数据")
    use_weather = st.checkbox("天气数据", value=False)
    use_bzzoiro_detail = st.checkbox("Bzzoiro深度（裁判+伤停）",
                                      value=False)

    st.divider()
    if st.button("🗑️ 清空赔率历史", use_container_width=True):
        clear_history()
        st.success("已清空")

    st.divider()
    with st.expander("🔑 Key 状态"):
        st.write(f"Parse.bot: {'✅' if PARSEBOT_API_KEY else '❌'}")
        st.write(f"TheOdds: {'✅' if THEODDS_API_KEY and len(THEODDS_API_KEY) == 32 else '❌'}")
        st.write(f"Bzzoiro: {'✅' if os.getenv('BZZOIRO_API_KEY') else '❌'}")

# 主区域
tab1, tab_near, tab2, tab3 = st.tabs(["🔮 今日分析", "🚨 临场检测", "📝 开云记录", "📜 历史记录"])

with tab1:
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        run_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)
    with col2:
        refresh_btn = st.button("🔄 刷新赔率", use_container_width=True)
    with col3:
        if st.button("🗑️ 清缓存", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("current_results", None)
            st.session_state.pop("current_report", None)
            st.success("已清")

    if refresh_btn:
        st.cache_data.clear()
        run_btn = True

    if run_btn:
        all_results = []

        # Bzzoiro
        if source in ("bzzoiro", "all"):
            progress = st.progress(0, text="准备拉取 Bzzoiro...")

            def cb(cur, total, name):
                progress.progress(cur / max(total, 1),
                                  text=f"[{cur}/{total}] {name}")

            with st.spinner("Bzzoiro 逐场拉赔率..."):
                try:
                    r, err = fetch_bzzoiro_matches(hours=hours, progress_cb=cb)
                    if r:
                        all_results.extend(r)
                        st.success(f"✅ Bzzoiro：{len(r)} 场")
                    elif err:
                        st.warning(f"Bzzoiro: {err}")
                    else:
                        st.info("Bzzoiro 返回 0 场（可能今日无赔率数据）")
                except Exception as e:
                    st.error(f"Bzzoiro 异常: {e}")
            progress.empty()

        # TheOdds
        if source in ("theodds", "all"):
            with st.spinner("拉取 TheOdds..."):
                try:
                    r, err = fetch_from_theodds()
                    if r:
                        all_results.extend(r)
                        st.success(f"✅ TheOdds：{len(r)} 场")
                except Exception as e:
                    st.warning(f"TheOdds: {e}")

        # 竞彩
        if source in ("sporttery", "all"):
            with st.spinner("拉取竞彩..."):
                try:
                    r, err = fetch_sporttery_matches()
                    if r:
                        all_results.extend(r)
                        st.success(f"✅ 竞彩：{len(r)} 场")
                except Exception as e:
                    st.warning(f"竞彩: {e}")

        if not all_results:
            st.error("没有拿到数据。")
            st.stop()

        deduped = _deduplicate(all_results)
        st.info(f"📥 原始 {len(all_results)} 场  去重 {len(deduped)} 场")

        results = _filter_by_hours(deduped, hours)
        st.info(f"⏰ 未来 {hours} 小时内：**{len(results)}** 场")

        if not results:
            st.warning("该时段无比赛。")
            st.stop()

        # 记录快照
        try:
            record_snapshot(results)
        except Exception:
            pass

        # 分析赔率变化
        for r in results:
            try:
                mv = analyze_movement(r.get("home", ""), r.get("away", ""))
                if mv:
                    r["movement_signal"] = mv["movement_signal"]
                    r["movement_note"] = mv["note"]
                    r["snapshots_count"] = mv["snapshots_count"]
                else:
                    r["movement_signal"] = None
                    r["movement_note"] = "首次"
                    r["snapshots_count"] = 1
            except Exception:
                r["movement_signal"] = None
                r["movement_note"] = ""

        # 天气
        if use_weather:
            with st.spinner("获取天气..."):
                try:
                    results = enrich_with_weather(results)
                except Exception as e:
                    st.warning(f"天气失败: {e}")

        # Bzzoiro 深度
        if use_bzzoiro_detail:
            with st.spinner("Bzzoiro 深度增强..."):
                try:
                    results = enrich_batch(results, max_count=15)
                except Exception as e:
                    st.warning(f"Bzzoiro: {e}")

        # 评分
        for r in results:
            try:
                rating = calc_rating(r)
                if rating:
                    r["score"] = rating["score"]
                    r["direction"] = rating["direction"]
                    r["confidence"] = rating["confidence"]
                    r["detail"] = rating["detail"]
            except Exception:
                r["score"] = None
                r["direction"] = "观望"
                r["confidence"] = 0

        # 展示
        st.subheader("📋 比赛列表")
        rows = []
        for r in results:
            src_label = {"bzzoiro": "Bzzoiro", "theodds": "TheOdds",
                         "sporttery": "竞彩", "parsebot": "Parse.bot"}.get(
                r.get("source"), "?")
            score = r.get("score")
            direction = r.get("direction")
            suggest = ""
            if score is not None and direction in ("大球", "小球"):
                try:
                    suggest = _suggest_odds(score, direction)
                except Exception:
                    suggest = ""

            ml = r.get("ml_over_prob")
            ml_str = f"{ml * 100:.1f}%" if ml else ""

            rows.append({
                "联赛": r.get("league_name", "") or cn_league(r.get("league", "")),
                "主队": cn_team(r.get("home", "")),
                "客队": cn_team(r.get("away", "")),
                "开赛": _format_kickoff(r.get("kickoff", "")),
                "倒计时": _countdown(r.get("kickoff", "")),
                "源": src_label,
                "盘口": r.get("live_line", ""),
                "大球": r.get("live_over", ""),
                "小球": r.get("live_under", ""),
                "ML预测": ml_str,
                "评分": score,
                "推荐": direction,
                "开云建议": suggest,
                "变化": r.get("movement_note", ""),
            })
        df = pd.DataFrame(rows)
        if "评分" in df.columns:
            df = df.sort_values("评分", ascending=False, na_position="last")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.session_state["current_results"] = results
        st.caption(f"🕐 数据时间：{datetime.now().strftime('%H:%M:%S')}")

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 导出 CSV", csv,
                           f"analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           "text/csv")

        try:
            report = generate_report(results, source=source,
                                     params={"mode": source, "hours": hours})
            st.session_state["current_report"] = report
        except Exception as e:
            st.warning(f"报告失败: {e}")

    # 开云录入
    if "current_results" in st.session_state:
        st.divider()
        st.subheader("✍️ 开云数据录入")

        results = st.session_state["current_results"]
        match_options = [
            f"{cn_team(r.get('home', ''))} vs {cn_team(r.get('away', ''))} "
            f"({_format_kickoff(r.get('kickoff', ''))})"
            for r in results
        ]

        if match_options:
            selected = st.selectbox("选择比赛", match_options, key="manual_select")
            idx = match_options.index(selected)
            target = results[idx]

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("评分", target.get("score", ""))
            with col_b:
                st.metric("推荐", target.get("direction", ""))
            with col_c:
                sv = ""
                if target.get("score"):
                    try:
                        sv = _suggest_odds(target["score"], target.get("direction"))
                    except Exception:
                        pass
                st.metric("开云建议", sv)

            existing = get_records(target.get("match_id", ""))
            if existing:
                st.dataframe(pd.DataFrame(existing),
                             use_container_width=True, hide_index=True)

            st.markdown("**新增开云数据**")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                stage = st.selectbox("阶段",
                                     ["赛前", "滚球", "中场", "75分钟", "赛后"],
                                     key="m_stage")
            with c2:
                line_val = st.number_input("盘口", 0.5, 5.0,
                                           float(target.get("live_line") or 2.5), 0.25)
            with c3:
                over_val = st.number_input("大球", 0.5, 20.0,
                                           float(target.get("live_over") or 1.80), 0.01)
            with c4:
                under_val = st.number_input("小球", 0.5, 20.0,
                                            float(target.get("live_under") or 2.00), 0.01)
            with c5:
                note = st.text_input("备注", value="", placeholder="升盘")

            if st.button("➕ 添加记录", type="primary"):
                match_name = (
                    f"{cn_team(target.get('home', ''))} "
                    f"vs {cn_team(target.get('away', ''))}"
                )
                try:
                    add_record(target.get("match_id", ""), match_name,
                               line_val, over_val, under_val,
                               note=f"[{stage}] {note}")
                    st.success("已添加")
                    st.rerun()
                except Exception as e:
                    st.error(f"失败: {e}")

    if "current_report" in st.session_state:
        st.divider()
        st.subheader("📄 分析报告")

        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.download_button(
                "⬇️ 下载报告 (.md)",
                st.session_state["current_report"].encode("utf-8"),
                f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md",
                "text/markdown",
                use_container_width=True,
            )
        with col_b:
            if st.button("🗑️ 清除报告", use_container_width=True,
                          key="clear_report_btn"):
                st.session_state.pop("current_report", None)
                st.rerun()

        st.info("💡 **复制方法**：把鼠标移到下面灰色代码框，**右上角会出现 📋 图标**，点它一键复制全部内容。")

        # st.code 自带右上角复制按钮
        st.code(st.session_state["current_report"], language="markdown")



# ============================================================
# Tab: 临场检测（快开赛比赛深度分析）
# ============================================================
with tab_near:
    st.subheader("🚨 临场检测")
    st.caption("只对快开赛的比赛做深度分析（天气+裁判+首发），速度更快")

    col_n1, col_n2 = st.columns([2, 2])
    with col_n1:
        near_hours = st.slider(
            "检测窗口（未来 N 小时内开赛的比赛）",
            min_value=1, max_value=12, value=3, step=1,
            help="默认 3 小时。赛前1小时效果最好",
        )
    with col_n2:
        near_source = st.selectbox(
            "数据源",
            ["Bzzoiro", "TheOdds", "竞彩", "全部整合"],
            index=0,
        )

    if st.button("🔍 开始临场检测", type="primary", use_container_width=True):
        all_near = []

        # 拉数据
        if near_source in ("Bzzoiro", "全部整合"):
            with st.spinner("拉取 Bzzoiro..."):
                try:
                    r, err = fetch_bzzoiro_matches(hours=near_hours)
                    if r:
                        all_near.extend(r)
                except Exception as e:
                    st.warning(f"Bzzoiro: {e}")

        if near_source in ("TheOdds", "全部整合"):
            with st.spinner("拉取 TheOdds..."):
                try:
                    r, err = fetch_from_theodds()
                    if r:
                        all_near.extend(r)
                except Exception as e:
                    st.warning(f"TheOdds: {e}")

        if near_source in ("竞彩", "全部整合"):
            with st.spinner("拉取竞彩..."):
                try:
                    r, err = fetch_sporttery_matches()
                    if r:
                        all_near.extend(r)
                except Exception as e:
                    st.warning(f"竞彩: {e}")

        if not all_near:
            st.error("没有数据。")
            st.stop()

        # 去重 + 严格筛选（未来 N 小时内）
        deduped_near = _deduplicate(all_near)

        now_bj = datetime.now(timezone(timedelta(hours=8)))
        deadline = now_bj + timedelta(hours=near_hours)
        near_results = []
        for r in deduped_near:
            dt = _parse_kickoff(r.get("kickoff"))
            if dt and now_bj < dt <= deadline:
                near_results.append(r)

        if not near_results:
            st.warning(f"未来 {near_hours} 小时内没有比赛。调大窗口。")
            st.stop()

        st.success(f"🔍 筛选出 **{len(near_results)}** 场快开赛比赛")

        # ⭐ 深度增强：天气
        with st.spinner("获取天气..."):
            try:
                near_results = enrich_with_weather(near_results)
            except Exception as e:
                st.warning(f"天气失败: {e}")

        # ⭐ 深度增强：裁判 + 首发
        with st.spinner(f"获取裁判+首发（{len(near_results)} 场，约 20~40 秒）..."):
            try:
                near_results = enrich_batch(near_results, max_count=20)
            except Exception as e:
                st.warning(f"裁判+首发失败: {e}")

        # 评分
        for r in near_results:
            try:
                rating = calc_rating(r)
                if rating:
                    r["score"] = rating["score"]
                    r["direction"] = rating["direction"]
                    r["confidence"] = rating["confidence"]
                    r["detail"] = rating["detail"]
            except Exception:
                r["score"] = None
                r["direction"] = "观望"

        # 展示
        st.markdown("### 📊 临场分析结果（按开赛时间排序）")
        near_results_sorted = sorted(
            near_results,
            key=lambda x: x.get("kickoff", "")
        )

        rows = []
        for r in near_results_sorted:
            src_label = {"bzzoiro": "Bzzoiro", "theodds": "TheOdds",
                         "sporttery": "竞彩"}.get(r.get("source"), "?")
            score = r.get("score")
            direction = r.get("direction")
            suggest = ""
            if score is not None and direction in ("大球", "小球"):
                try:
                    suggest = _suggest_odds(score, direction)
                except Exception:
                    pass

            # 天气
            wt = r.get("weather_temp")
            ww = r.get("weather_wind")
            wr = r.get("weather_rain")
            w_note = r.get("weather_note", "")

            rows.append({
                "倒计时": _countdown(r.get("kickoff", "")),
                "开赛": _format_kickoff(r.get("kickoff", "")),
                "联赛": r.get("league_name", "") or cn_league(r.get("league", "")),
                "主队": cn_team(r.get("home", "")),
                "客队": cn_team(r.get("away", "")),
                "源": src_label,
                "盘口": r.get("live_line", ""),
                "大球": r.get("live_over", ""),
                "小球": r.get("live_under", ""),
                "评分": score,
                "推荐": direction,
                "开云建议": suggest,
                "天气": w_note,
                "裁判": r.get("referee_note", ""),
                "首发": r.get("lineup_note", ""),
            })

        df_near = pd.DataFrame(rows)
        st.dataframe(df_near, use_container_width=True, hide_index=True)

        # 详细卡片
        st.markdown("### 🔍 逐场详细分析")
        for r in near_results_sorted:
            home_cn = cn_team(r.get("home", ""))
            away_cn = cn_team(r.get("away", ""))
            countdown = _countdown(r.get("kickoff", ""))

            with st.expander(
                f"⚽ {home_cn} vs {away_cn} ｜ ⏰ {countdown} ｜ "
                f"评分 {r.get('score', '')} ｜ {r.get('direction', '')}",
                expanded=(countdown in ("1小时", "2小时") or "分" in countdown),
            ):
                col_x, col_y, col_z = st.columns(3)

                with col_x:
                    st.markdown("**📊 赔率**")
                    st.write(f"盘口：{r.get('live_line', '')}")
                    st.write(f"大球：{r.get('live_over', '')}")
                    st.write(f"小球：{r.get('live_under', '')}")
                    st.write(f"开云建议：{_suggest_odds(r.get('score'), r.get('direction')) if r.get('score') else ''}")

                with col_y:
                    st.markdown("**🌤️ 天气**")
                    st.write(f"温度：{r.get('weather_temp', '')}C")
                    st.write(f"风速：{r.get('weather_wind', '')} km/h")
                    st.write(f"降水：{r.get('weather_rain', '')} mm")
                    st.caption(r.get("weather_note", ""))

                with col_z:
                    st.markdown("**👨‍⚖️ 裁判**")
                    st.write(r.get("referee_note", ""))
                    st.markdown("**👥 首发**")
                    st.write(r.get("lineup_note", ""))

                # 评分明细
                if r.get("detail"):
                    st.caption(f"📈 评分明细：{r['detail']}")

        st.session_state["near_results"] = near_results

        # 报告按钮
        st.divider()
        if st.button("📄 生成临场报告", key="gen_near_report"):
            try:
                report = generate_report(
                    near_results, source=f"临场检测({near_source})",
                    params={"hours": near_hours},
                )
                st.session_state["near_report"] = report
            except Exception as e:
                st.error(f"生成失败: {e}")

        if "near_report" in st.session_state:
            st.info("💡 鼠标移到代码框右上角，点 📋 一键复制")
            st.code(st.session_state["near_report"], language="markdown")


with tab2:
    st.subheader("📝 开云赔率记录")
    data = get_all()
    if not data:
        st.info("暂无记录。")
    else:
        for mid, info in data.items():
            recs = info.get("records", [])
            if not recs:
                continue
            with st.expander(f"⚽ {info.get('match_name', mid)} （{len(recs)} 条）"):
                st.dataframe(pd.DataFrame(recs),
                             use_container_width=True, hide_index=True)
                if len(recs) >= 2:
                    f, l = recs[0], recs[-1]
                    try:
                        oc = float(l["over"]) - float(f["over"])
                        uc = float(l["under"]) - float(f["under"])
                        lc = float(l["line"]) - float(f["line"])
                        st.markdown(f"**变化**：大球 {oc:+.2f} | 小球 {uc:+.2f} | 盘口 {lc:+.2f}")
                    except Exception:
                        pass
                if st.button("🗑️ 删除", key=f"delm_{mid}"):
                    delete_match(mid)
                    st.rerun()


with tab3:
    st.subheader("📜 历史记录")
    files = list_history()
    if not files:
        st.info("暂无历史。")
    else:
        labels = [format_label(f) for f in files]
        sel = st.selectbox("选择记录", labels)
        if sel:
            idx = labels.index(sel)
            data = load_history(files[idx])
            if data:
                c1, c2, c3 = st.columns(3)
                c1.metric("时间", data.get("timestamp", ""))
                c2.metric("数据源", data.get("source", ""))
                c3.metric("场次", data.get("count", 0))
                results = data.get("results", [])
                if results:
                    df_h = pd.DataFrame(results)
                    for col, func in [("league", cn_league),
                                      ("home", cn_team), ("away", cn_team)]:
                        if col in df_h.columns:
                            df_h[col] = df_h[col].apply(func)
                    cols = [c for c in ["league", "home", "away",
                                          "live_over", "live_under", "live_line",
                                          "score", "direction"]
                            if c in df_h.columns]
                    st.dataframe(df_h[cols], use_container_width=True, hide_index=True)
                if st.button("🗑️ 删除", key=f"del_{files[idx]}"):
                    delete_history(files[idx])
                    st.rerun()


st.divider()
st.caption("⚠️ 数据分析辅助，不构成投注建议。")
