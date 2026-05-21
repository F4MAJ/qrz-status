#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Génère un badge météo SVG pour la page QRZ F4MAJ.

Sortie :
docs/meteo-f4maj.svg

Source météo :
Open-Meteo, position approximative Illzach / JN37QS.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


OUTPUT_FILE = Path("docs/meteo-f4maj.svg")

LATITUDE = 47.7813
LONGITUDE = 7.3469
TIMEZONE = "Europe/Paris"

WEATHERCLOUD_URL = "https://app.weathercloud.net/d8858120004#current"


def weather_label(code: int | None) -> str:
    labels = {
        0: "Ciel clair",
        1: "Peu nuageux",
        2: "Partiellement nuageux",
        3: "Couvert",
        45: "Brouillard",
        48: "Brouillard givrant",
        51: "Bruine faible",
        53: "Bruine modérée",
        55: "Bruine forte",
        61: "Pluie faible",
        63: "Pluie modérée",
        65: "Pluie forte",
        71: "Neige faible",
        73: "Neige modérée",
        75: "Neige forte",
        80: "Averses faibles",
        81: "Averses modérées",
        82: "Averses fortes",
        95: "Orage",
        96: "Orage avec grêle",
        99: "Orage fort avec grêle",
    }
    return labels.get(code, "Conditions variables")


def svg_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fetch_weather() -> dict:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "weather_code",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "precipitation",
            ]
        ),
        "timezone": TIMEZONE,
    }

    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "F4MAJ-QRZ-Weather-Badge/1.1",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def format_time(value: str | None) -> str:
    if not value:
        return datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")

    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def safe_number(value: object, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "--"


def build_svg(data: dict) -> str:
    current = data.get("current", {})

    temperature = safe_number(current.get("temperature_2m"), 1)
    humidity = safe_number(current.get("relative_humidity_2m"), 0)
    apparent = safe_number(current.get("apparent_temperature"), 1)
    pressure = safe_number(current.get("pressure_msl"), 0)
    wind = safe_number(current.get("wind_speed_10m"), 0)
    wind_dir = safe_number(current.get("wind_direction_10m"), 0)
    precipitation = safe_number(current.get("precipitation"), 1)

    code = current.get("weather_code")
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        code_int = None

    condition = weather_label(code_int)
    update_time = format_time(current.get("time"))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="250" viewBox="0 0 1120 250">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#172033"/>
      <stop offset="65%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1f2937"/>
    </linearGradient>

    <linearGradient id="card" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1e293b"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>

    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.32"/>
    </filter>
  </defs>

  <rect x="8" y="8" width="1104" height="234" rx="22" fill="url(#bg)" stroke="#334155" stroke-width="2" filter="url(#shadow)"/>

  <text x="34" y="45" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700" fill="#ffffff">
    Météo live au QRA F4MAJ
  </text>

  <text x="34" y="76" font-family="Arial, Helvetica, sans-serif" font-size="16" fill="#cbd5e1">
    Illzach • JN37QS • aperçu météo automatique — {svg_escape(condition)}
  </text>

  <text x="850" y="45" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#fbbf24">
    Station WeatherCloud F4MAJ
  </text>

  <text x="850" y="70" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#94a3b8">
    Données indicatives pour le secteur du QRA
  </text>

  <g transform="translate(34,105)">
    <rect x="0" y="0" width="195" height="92" rx="16" fill="url(#card)" stroke="#334155"/>
    <text x="18" y="30" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#fbbf24">🌡 Température</text>
    <text x="18" y="62" font-family="Arial, Helvetica, sans-serif" font-size="27" font-weight="700" fill="#ffffff">{temperature} °C</text>
    <text x="18" y="82" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#94a3b8">Ressenti : {apparent} °C</text>
  </g>

  <g transform="translate(249,105)">
    <rect x="0" y="0" width="195" height="92" rx="16" fill="url(#card)" stroke="#334155"/>
    <text x="18" y="30" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#fbbf24">💧 Humidité</text>
    <text x="18" y="66" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" fill="#ffffff">{humidity} %</text>
  </g>

  <g transform="translate(464,105)">
    <rect x="0" y="0" width="195" height="92" rx="16" fill="url(#card)" stroke="#334155"/>
    <text x="18" y="30" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#fbbf24">🌬 Vent</text>
    <text x="18" y="62" font-family="Arial, Helvetica, sans-serif" font-size="27" font-weight="700" fill="#ffffff">{wind} km/h</text>
    <text x="18" y="82" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#94a3b8">Direction : {wind_dir}°</text>
  </g>

  <g transform="translate(679,105)">
    <rect x="0" y="0" width="195" height="92" rx="16" fill="url(#card)" stroke="#334155"/>
    <text x="18" y="30" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#fbbf24">📊 Pression</text>
    <text x="18" y="66" font-family="Arial, Helvetica, sans-serif" font-size="28" font-weight="700" fill="#ffffff">{pressure} hPa</text>
  </g>

  <g transform="translate(894,105)">
    <rect x="0" y="0" width="195" height="92" rx="16" fill="url(#card)" stroke="#334155"/>
    <text x="18" y="30" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#fbbf24">🕒 Mise à jour</text>
    <text x="18" y="58" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#ffffff">{svg_escape(update_time)}</text>
    <text x="18" y="82" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#94a3b8">Pluie : {precipitation} mm</text>
  </g>

  <text x="34" y="224" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#94a3b8">
    Source météo automatique • affichage QRZ sans iframe ni widget externe • lien station : {svg_escape(WEATHERCLOUD_URL)}
  </text>
</svg>
'''


def build_error_svg(message: str) -> str:
    safe_message = svg_escape(message)
    update_time = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1120" height="250" viewBox="0 0 1120 250">
  <rect x="8" y="8" width="1104" height="234" rx="22" fill="#111827" stroke="#334155" stroke-width="2"/>
  <text x="34" y="55" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700" fill="#ffffff">
    Météo live au QRA F4MAJ
  </text>
  <text x="34" y="95" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#f59e0b">
    Vérification météo temporairement indisponible
  </text>
  <text x="34" y="130" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#cbd5e1">
    {safe_message}
  </text>
  <text x="34" y="165" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#94a3b8">
    Dernier essai : {update_time}
  </text>
</svg>
'''


def main() -> int:
    try:
        data = fetch_weather()
        svg = build_svg(data)
    except Exception as exc:
        print(f"Weather update failed: {exc}")
        svg = build_error_svg(str(exc))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    old_content = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else None

    if old_content == svg:
        print("No weather badge change.")
        return 0

    OUTPUT_FILE.write_text(svg, encoding="utf-8")
    print(f"Weather badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
