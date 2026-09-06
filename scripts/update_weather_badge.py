#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Génère le badge météo SVG pour la page QRZ F4MAJ.

Version V3 :
- source météo : Open-Meteo, position approximative Illzach / JN37QS
- affichage QRZ sans iframe ni widget externe
- "Mise à jour" = heure réelle de génération du badge par GitHub Actions
- "Mesure" = heure de la donnée météo renvoyée par Open-Meteo
- largeur SVG augmentée à 1200 px pour éviter les débordements à droite
- texte haut droit et ligne basse raccourcis pour éviter toute coupure
- sortie : docs/meteo-f4maj.svg
- en cas d’erreur de source, conserver le dernier badge sans modifier sa date
"""

from __future__ import annotations

import html
import json
import math
import os
import tempfile
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
    return html.escape("" if value is None else str(value), quote=True)


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
            "User-Agent": "F4MAJ-QRZ-Weather-Badge/3.0",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)


def safe_number(value: object, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return "--"


def generated_time() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def weather_measure_time(value: str | None) -> str:
    if not value:
        return "--"

    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d/%m/%Y %H:%M")
    except ValueError:
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

    try:
        code_int = int(current.get("weather_code"))
    except (TypeError, ValueError):
        code_int = None

    condition = weather_label(code_int)

    badge_update_time = generated_time()
    measure_time = weather_measure_time(current.get("time"))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="236" viewBox="0 0 1200 236" role="img" aria-label="Météo live au QRA F4MAJ">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>

    <linearGradient id="card" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#172033"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>

    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="6" flood-color="#000000" flood-opacity="0.35"/>
    </filter>
  </defs>

  <!-- Badge météo F4MAJ V3 / génération : {svg_escape(badge_update_time)} -->

  <rect x="1" y="1" width="1198" height="234" rx="22" fill="url(#bg)" stroke="#334155" stroke-width="2" filter="url(#shadow)"/>

  <text x="28" y="39" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">
    Météo live au QRA F4MAJ
  </text>

  <text x="28" y="70" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="500" fill="#dbeafe">
    Illzach • JN37QS • aperçu météo automatique — {svg_escape(condition)}
  </text>

  <text x="848" y="39" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700" fill="#fbbf24">
    Station WeatherCloud F4MAJ
  </text>

  <text x="848" y="68" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    Données indicatives secteur QRA
  </text>

  <!-- Carte Température -->
  <rect x="28" y="96" width="201" height="96" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="51" y="125" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#fbbf24">🌡️ Température</text>
  <text x="47" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{temperature} °C</text>
  <text x="47" y="184" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="500" fill="#bfdbfe">Ressenti : {apparent} °C</text>

  <!-- Carte Humidité -->
  <rect x="243" y="96" width="201" height="96" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="266" y="125" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#fbbf24">💧 Humidité</text>
  <text x="261" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{humidity} %</text>

  <!-- Carte Vent -->
  <rect x="458" y="96" width="201" height="96" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="481" y="125" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#fbbf24">🌬️ Vent</text>
  <text x="476" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{wind} km/h</text>
  <text x="476" y="184" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="500" fill="#bfdbfe">Direction : {wind_dir}°</text>

  <!-- Carte Pression -->
  <rect x="673" y="96" width="201" height="96" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="696" y="125" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#fbbf24">📊 Pression</text>
  <text x="690" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{pressure} hPa</text>

  <!-- Carte Mise à jour -->
  <rect x="888" y="96" width="201" height="96" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="911" y="125" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#fbbf24">🕘 Mise à jour</text>
  <text x="902" y="151" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" fill="#ffffff">{svg_escape(badge_update_time)}</text>
  <text x="902" y="174" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="500" fill="#bfdbfe">Mesure : {svg_escape(measure_time)}</text>
  <text x="902" y="188" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="500" fill="#bfdbfe">Pluie : {precipitation} mm</text>

  <text x="28" y="222" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="500" fill="#bfdbfe">
    Source météo automatique • QRZ sans iframe ni widget externe • station WeatherCloud F4MAJ
  </text>
</svg>
'''


def validate_weather(data: dict) -> None:
    """Do not replace a good badge with an empty or invalid source response."""
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("Invalid weather source response")
    current = data.get("current")
    if not isinstance(current, dict):
        raise ValueError("Missing current weather")
    if not isinstance(current.get("time"), str):
        raise ValueError("Missing weather measurement time")
    datetime.fromisoformat(current["time"])
    for field in (
        "temperature_2m", "relative_humidity_2m", "apparent_temperature",
        "weather_code", "pressure_msl", "wind_speed_10m",
        "wind_direction_10m", "precipitation",
    ):
        value = current.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Missing or invalid weather field: {field}")
        if not math.isfinite(value):
            raise ValueError(f"Non-finite weather field: {field}")


def main() -> int:
    try:
        data = fetch_weather()
        validate_weather(data)
        svg = build_svg(data)
        current = data.get("current", {})
        print(f"Weather source time: {current.get('time') or '-'}")
        print(f"Badge generated time: {generated_time()}")
    except Exception as exc:
        print(f"Weather update failed: {exc}")
        if OUTPUT_FILE.is_file():
            print(f"Keeping existing weather badge unchanged: {OUTPUT_FILE}")
            return 0
        print("No existing weather badge to keep; no error SVG written.")
        return 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    old_content = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else None

    if old_content == svg:
        print("No weather badge change.")
        return 0

    # Replace only after the complete SVG has been written successfully.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=OUTPUT_FILE.parent,
            prefix=OUTPUT_FILE.name + ".", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(svg)
        os.replace(temporary_path, OUTPUT_FILE)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(f"Weather badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

