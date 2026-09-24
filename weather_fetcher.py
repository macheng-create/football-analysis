# -*- coding: utf-8 -*-
"""weather_fetcher.py - 比赛天气数据（Open-Meteo，免费）"""

import requests
import streamlit as st


# 联赛/国家队  城市映射
CITY_MAP = {
    # 五大联赛（用联赛所在国主要城市近似）
    "soccer_epl": "London",
    "soccer_efl_champ": "London",
    "soccer_spain_la_liga": "Madrid",
    "soccer_spain_segunda_division": "Madrid",
    "soccer_italy_serie_a": "Milan",
    "soccer_italy_serie_b": "Milan",
    "soccer_germany_bundesliga": "Munich",
    "soccer_germany_bundesliga2": "Munich",
    "soccer_france_ligue_one": "Paris",
    "soccer_france_ligue_two": "Paris",
    "soccer_uefa_champs_league": "London",
    "soccer_uefa_europa_league": "London",
    "soccer_uefa_europa_conference_league": "London",
    "soccer_uefa_nations_league": None,  # 按主队判断
    "soccer_netherlands_eredivisie": "Amsterdam",
    "soccer_portugal_primeira_liga": "Lisbon",
    "soccer_belgium_first_div": "Brussels",
    "soccer_turkey_super_league": "Istanbul",
    "soccer_usa_mls": "New York",
    "soccer_mexico_ligamx": "Mexico City",
    "soccer_brazil_campeonato": "Sao Paulo",
    "soccer_argentina_primera_division": "Buenos Aires",
    "soccer_korea_kleague1": "Seoul",
    "soccer_australia_aleague": "Sydney",
    "soccer_conmebol_copa_libertadores": "Buenos Aires",
    # 竞彩联赛名（中文）
    "英超": "London", "英冠": "London", "英联赛杯": "London",
    "西甲": "Madrid", "西乙": "Madrid",
    "意甲": "Milan", "意乙": "Milan",
    "德甲": "Munich", "德乙": "Munich", "德丙": "Munich", "德国杯": "Berlin",
    "法甲": "Paris", "法乙": "Paris",
    "欧冠": "London", "欧联": "London", "欧协联": "London",
    "欧国联": None,
    "荷甲": "Amsterdam", "葡超": "Lisbon", "比甲": "Brussels",
    "土超": "Istanbul", "美职": "New York", "墨超": "Mexico City",
    "巴甲": "Sao Paulo", "阿甲": "Buenos Aires",
}


# 国家队  首都
NATIONAL_CITY_MAP = {
    # 国家队（欧国联等）
    "Andorra": "Andorra la Vella",
    "Malta": "Valletta",
    "Austria": "Vienna",
    "Israel": "Jerusalem",
    "Norway": "Oslo",
    "Denmark": "Copenhagen",
    "Netherlands": "Amsterdam",
    "Germany": "Berlin",
    "Serbia": "Belgrade",
    "Greece": "Athens",
    "Kosovo": "Pristina",
    "Republic of Ireland": "Dublin",
    "Ireland": "Dublin",
    "Liechtenstein": "Vaduz",
    "Lithuania": "Vilnius",
    "Portugal": "Lisbon",
    "Wales": "Cardiff",
    "Armenia": "Yerevan",
    "Latvia": "Riga",
    "Georgia": "Tbilisi",
    "Northern Ireland": "Belfast",
    "Italy": "Rome",
    "Belgium": "Brussels",
    "Poland": "Warsaw",
    "Bosnia & Herzegovina": "Sarajevo",
    "Montenegro": "Podgorica",
    "Cyprus": "Nicosia",
    "Turkey": "Istanbul",
    "France": "Paris",
    "Hungary": "Budapest",
    "Ukraine": "Kyiv",
    "Sweden": "Stockholm",
    "Romania": "Bucharest",
    "Slovenia": "Ljubljana",
    "Scotland": "Edinburgh",
    "Bulgaria": "Sofia",
    "Luxembourg": "Luxembourg",
    "Iceland": "Reykjavik",
    "Estonia": "Tallinn",
    "Faroe Islands": "Torshavn",
    "Kazakhstan": "Astana",
    "Spain": "Madrid",
    "Switzerland": "Bern",
    "Czech Republic": "Prague",
    "Czechia": "Prague",
    "Croatia": "Zagreb",
    "Finland": "Helsinki",
    "Albania": "Tirana",
    "Belarus": "Minsk",
    "England": "London",
    "Slovakia": "Bratislava",
    "North Macedonia": "Skopje",
    "Moldova": "Chisinau",
    "San Marino": "San Marino",
    "Gibraltar": "Gibraltar",
    "Azerbaijan": "Baku",
    # 主要俱乐部所在城市
    "Arsenal": "London", "Chelsea": "London", "Tottenham": "London",
    "Tottenham Hotspur": "London", "West Ham United": "London",
    "Crystal Palace": "London", "Fulham": "London", "Brentford": "London",
    "Manchester City": "Manchester", "Manchester United": "Manchester",
    "Liverpool": "Liverpool", "Everton": "Liverpool",
    "Newcastle United": "Newcastle", "Aston Villa": "Birmingham",
    "Real Madrid": "Madrid", "Atletico Madrid": "Madrid",
    "Atlético Madrid": "Madrid", "Real Betis": "Seville",
    "Sevilla": "Seville", "Barcelona": "Barcelona", "Espanyol": "Barcelona",
    "Bayern Munich": "Munich", "Borussia Dortmund": "Dortmund",
    "RB Leipzig": "Leipzig", "Bayer Leverkusen": "Leverkusen",
    "Inter Milan": "Milan", "AC Milan": "Milan", "Inter": "Milan",
    "Juventus": "Turin", "Napoli": "Naples", "AS Roma": "Rome",
    "Lazio": "Rome", "Fiorentina": "Florence",
    "Paris Saint Germain": "Paris", "PSG": "Paris",
    "Marseille": "Marseille", "Lyon": "Lyon", "Monaco": "Monaco",
    "AS Monaco": "Monaco", "Lille": "Lille",
    "Ajax": "Amsterdam", "Feyenoord": "Rotterdam",
    "PSV Eindhoven": "Eindhoven", "PSV": "Eindhoven",
    "Porto": "Porto", "Benfica": "Lisbon", "Sporting CP": "Lisbon",
    "Sporting Lisbon": "Lisbon",
    "Galatasaray": "Istanbul", "Fenerbahce": "Istanbul",
    "Celtic": "Glasgow", "Rangers": "Glasgow",
    "Salzburg": "Salzburg", "Red Bull Salzburg": "Salzburg",
    "Young Boys": "Bern", "FC Copenhagen": "Copenhagen",
}


@st.cache_data(ttl=1800, show_spinner=False)
def _get_weather(city):
    """获取城市当前天气（缓存 30 分钟）"""
    try:
        # 地理编码
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_r = requests.get(geo_url, params={"name": city, "count": 1}, timeout=8)
        if geo_r.status_code != 200:
            return None

        geo_data = geo_r.json()
        results = geo_data.get("results", [])
        if not results:
            return None

        lat = results[0]["latitude"]
        lon = results[0]["longitude"]

        # 天气
        weather_url = "https://api.open-meteo.com/v1/forecast"
        w_r = requests.get(
            weather_url,
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,wind_speed_10m,precipitation",
                "timezone": "auto",
            },
            timeout=8,
        )
        if w_r.status_code != 200:
            return None

        w_data = w_r.json().get("current", {})
        return {
            "temp": w_data.get("temperature_2m"),
            "wind": w_data.get("wind_speed_10m"),
            "rain": w_data.get("precipitation"),
        }
    except Exception:
        return None


def _find_city(home_team, away_team, league):
    """按主队名 / 联赛找城市"""
    # 优先球队精确匹配
    for team in [home_team, away_team]:
        if team in NATIONAL_CITY_MAP:
            return NATIONAL_CITY_MAP[team]
    # 用联赛映射
    city = CITY_MAP.get(league)
    if city:
        return city
    return None


def calc_weather_score(weather):
    """天气  大小球加分"""
    if not weather:
        return 0, 0, "无数据"

    over_bonus = 0
    under_bonus = 0
    notes = []

    temp = weather.get("temp")
    wind = weather.get("wind")
    rain = weather.get("rain")

    if temp is not None:
        if temp < 5:
            under_bonus += 4
            notes.append(f"{temp}C")
        elif temp > 32:
            under_bonus += 3
            notes.append(f"{temp}C")

    if wind is not None:
        if wind > 30:
            under_bonus += 8
            notes.append(f"大风{wind}km/h")
        elif wind > 20:
            under_bonus += 3
            notes.append(f"有风{wind}km/h")

    if rain is not None and rain > 2:
        under_bonus += 6
        notes.append(f"降雨{rain}mm")

    return over_bonus, under_bonus, "; ".join(notes) if notes else "正常"


def enrich_with_weather(results, max_matches=50):
    """给结果列表批量加天气字段（只处理前 N 场，避免太慢）"""
    if not results:
        return results

    for i, r in enumerate(results):
        if i >= max_matches:
            r["weather_temp"] = None
            r["weather_wind"] = None
            r["weather_rain"] = None
            r["weather_note"] = "未查询"
            r["weather_over_bonus"] = 0
            r["weather_under_bonus"] = 0
            continue

        city = _find_city(r.get("home", ""), r.get("away", ""), r.get("league", ""))
        if not city:
            r["weather_temp"] = None
            r["weather_wind"] = None
            r["weather_rain"] = None
            r["weather_note"] = "无城市"
            r["weather_over_bonus"] = 0
            r["weather_under_bonus"] = 0
            continue

        weather = _get_weather(city)
        if not weather:
            r["weather_temp"] = None
            r["weather_wind"] = None
            r["weather_rain"] = None
            r["weather_note"] = "获取失败"
            r["weather_over_bonus"] = 0
            r["weather_under_bonus"] = 0
            continue

        over, under, note = calc_weather_score(weather)
        r["weather_temp"] = weather.get("temp")
        r["weather_wind"] = weather.get("wind")
        r["weather_rain"] = weather.get("rain")
        r["weather_note"] = f"{city}: {note}"
        r["weather_over_bonus"] = over
        r["weather_under_bonus"] = under

    return results
