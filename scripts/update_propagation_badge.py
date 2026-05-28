#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Badge dynamique Propagation HF F4MAJ pour QRZ.

Version V1.2 :
- sources : HamQSL/N0NBH + NOAA/SWPC
- indicateurs : SFI, Kp, A-index, X-Ray, tendance HF, radio en extérieur
- affichage X-Ray : Classe A/B/C/M/X
- libellé mise à jour corrigé : auto horaire • minute 23
- sortie : docs/propagation-f4maj.svg
"""

from __future__ import annotations

import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo


OUTPUT_FILE = Path("docs/propagation-f4maj.svg")

TIMEZONE = "Europe/Paris"

HAMQSL_XML_URL = "https://www.hamqsl.com/solarxml.php"
NOAA_KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
NOAA_XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"

SOURCE_LABEL = "Sources : NOAA/SWPC + HamQSL/N0NBH"


def now_fr() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def svg_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fetch_text(url: str, timeout: int = 25) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "F4MAJ-QRZ-Propagation-Badge/1.2",
            "Accept": "application/json,text/xml,application/xml,text/plain,*/*",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def normalize(value: object) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = text.replace("\xa0", " ")
    return " ".join(text.split())


def safe_float(value: object) -> Optional[float]:
    try:
        text = normalize(value).replace(",", ".")
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0))
    except Exception:
        return None


def parse_hamqsl_xml(text: str) -> dict[str, str]:
    data: dict[str, str] = {}

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return data

    for element in root.iter():
        tag = element.tag.lower().strip()
        if element.text:
            data[tag] = normalize(element.text)

    return data


def fetch_hamqsl_data() -> dict[str, Any]:
    try:
        text = fetch_text(HAMQSL_XML_URL)
        parsed = parse_hamqsl_xml(text)
        return {
            "ok": True,
            "data": parsed,
            "error": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "data": {},
            "error": str(exc),
        }


def fetch_noaa_kp() -> dict[str, Any]:
    try:
        text = fetch_text(NOAA_KP_URL)
        payload = json.loads(text)

        if not isinstance(payload, list) or len(payload) < 2:
            return {"ok": False, "kp": None, "time": "", "error": "Format Kp NOAA inattendu"}

        headers = [str(h).lower() for h in payload[0]]
        last = payload[-1]

        kp_index = None
        time_index = None

        for index, header in enumerate(headers):
            if "kp" in header:
                kp_index = index
            if "time" in header or "date" in header:
                time_index = index

        if kp_index is None:
            return {"ok": False, "kp": None, "time": "", "error": "Colonne Kp introuvable"}

        kp_value = safe_float(last[kp_index])
        time_value = normalize(last[time_index]) if time_index is not None and time_index < len(last) else ""

        return {
            "ok": kp_value is not None,
            "kp": kp_value,
            "time": time_value,
            "error": "" if kp_value is not None else "Valeur Kp introuvable",
        }

    except Exception as exc:
        return {
            "ok": False,
            "kp": None,
            "time": "",
            "error": str(exc),
        }


def xray_flux_to_class(flux: float) -> str:
    if flux >= 1e-4:
        return "X"
    if flux >= 1e-5:
        return "M"
    if flux >= 1e-6:
        return "C"
    if flux >= 1e-7:
        return "B"
    if flux >= 1e-8:
        return "A"
    return "Très faible"


def fetch_noaa_xray() -> dict[str, Any]:
    try:
        text = fetch_text(NOAA_XRAY_URL)
        payload = json.loads(text)

        if not isinstance(payload, list) or not payload:
            return {"ok": False, "class": "", "flux": None, "time": "", "error": "Format X-Ray NOAA inattendu"}

        for item in reversed(payload):
            if not isinstance(item, dict):
                continue

            flux = safe_float(item.get("flux"))
            if flux is None:
                continue

            observed = normalize(item.get("time_tag") or item.get("time") or "")
            x_class = xray_flux_to_class(flux)

            return {
                "ok": True,
                "class": x_class,
                "flux": flux,
                "time": observed,
                "error": "",
            }

        return {"ok": False, "class": "", "flux": None, "time": "", "error": "Aucun flux X-Ray valide"}

    except Exception as exc:
        return {
            "ok": False,
            "class": "",
            "flux": None,
            "time": "",
            "error": str(exc),
        }


def condition_from_kp(kp: Optional[float]) -> tuple[str, str]:
    if kp is None:
        return "Non dispo", "Indicateur Kp non disponible"

    if kp < 3:
        return "Calme", "Champ géomagnétique calme"
    if kp < 5:
        return "Instable", "Conditions géomagnétiques à surveiller"
    if kp < 7:
        return "Perturbé", "Risque de dégradation HF"
    return "Tempête", "Conditions HF difficiles possibles"


def hf_trend(sfi: Optional[float], kp: Optional[float], xray_class: str) -> tuple[str, str]:
    if kp is not None and kp >= 6:
        return "Difficile", "Kp élevé, HF possiblement instable"

    if xray_class in ("M", "X"):
        return "À surveiller", "Risque de blackout HF côté jour"

    if sfi is not None and sfi >= 130 and (kp is None or kp < 4):
        return "Favorable", "Bon potentiel HF, surtout bandes hautes"

    if sfi is not None and sfi >= 90 and (kp is None or kp < 5):
        return "Correcte", "Conditions HF utilisables"

    if kp is not None and kp >= 4:
        return "Moyenne", "Propagation variable"

    return "Moyenne", "Conditions indicatives normales"


def portable_trend(kp: Optional[float], xray_class: str) -> tuple[str, str]:
    if kp is not None and kp >= 6:
        return "À éviter", "Perturbations fortes possibles"

    if xray_class in ("M", "X"):
        return "À surveiller", "Risque de coupure HF côté jour"

    if kp is not None and kp >= 4:
        return "Correcte", "Sortie possible, conditions variables"

    return "Favorable", "Bon contexte radio en extérieur"


def format_num(value: Optional[float], decimals: int = 0) -> str:
    if value is None:
        return "--"
    if decimals == 0:
        return str(int(round(value)))
    return f"{value:.{decimals}f}"


def collect_data() -> dict[str, Any]:
    hamqsl = fetch_hamqsl_data()
    noaa_kp = fetch_noaa_kp()
    noaa_xray = fetch_noaa_xray()

    hdata = hamqsl.get("data", {}) if hamqsl.get("ok") else {}

    sfi = safe_float(hdata.get("solarflux") or hdata.get("sfi"))
    aindex = safe_float(hdata.get("aindex") or hdata.get("a-index") or hdata.get("a"))

    kp_hamqsl = safe_float(hdata.get("kindex") or hdata.get("k-index") or hdata.get("k"))
    kp_noaa = noaa_kp.get("kp") if noaa_kp.get("ok") else None
    kp = kp_noaa if kp_noaa is not None else kp_hamqsl

    xray_hamqsl = normalize(hdata.get("xray"))
    xray_noaa_class = normalize(noaa_xray.get("class")) if noaa_xray.get("ok") else ""
    xray = xray_noaa_class or xray_hamqsl or "--"

    geomag, geomag_note = condition_from_kp(kp)
    hf_status, hf_note = hf_trend(sfi, kp, xray)
    portable_status, portable_note = portable_trend(kp, xray)

    updated_hamqsl = normalize(hdata.get("updated"))
    generated = now_fr()

    return {
        "sfi": sfi,
        "aindex": aindex,
        "kp": kp,
        "xray": xray,
        "geomag": geomag,
        "geomag_note": geomag_note,
        "hf_status": hf_status,
        "hf_note": hf_note,
        "portable_status": portable_status,
        "portable_note": portable_note,
        "updated_hamqsl": updated_hamqsl,
        "generated": generated,
        "hamqsl_ok": bool(hamqsl.get("ok")),
        "noaa_kp_ok": bool(noaa_kp.get("ok")),
        "noaa_xray_ok": bool(noaa_xray.get("ok")),
        "hamqsl_error": hamqsl.get("error") or "",
        "noaa_kp_error": noaa_kp.get("error") or "",
        "noaa_xray_error": noaa_xray.get("error") or "",
    }


def status_color(status: str) -> str:
    lowered = status.lower()

    if "favorable" in lowered or "calme" in lowered:
        return "#22c55e"

    if "correct" in lowered or "moyenne" in lowered or "instable" in lowered:
        return "#fbbf24"

    if "surveiller" in lowered or "perturb" in lowered:
        return "#f97316"

    if "difficile" in lowered or "tempête" in lowered or "éviter" in lowered:
        return "#ef4444"

    return "#38bdf8"


def build_svg(data: dict[str, Any]) -> str:
    sfi = format_num(data.get("sfi"), 0)
    kp = format_num(data.get("kp"), 1)
    aindex = format_num(data.get("aindex"), 0)

    xray = normalize(data.get("xray")) or "--"
    xray_display = f"Classe {xray}" if xray in ("A", "B", "C", "M", "X") else xray

    geomag = normalize(data.get("geomag")) or "--"
    hf_status = normalize(data.get("hf_status")) or "--"
    hf_note = normalize(data.get("hf_note")) or ""
    portable_status = normalize(data.get("portable_status")) or "--"
    portable_note = normalize(data.get("portable_note")) or ""

    generated = normalize(data.get("generated")) or now_fr()
    hamqsl_updated = normalize(data.get("updated_hamqsl"))

    hf_color = status_color(hf_status)
    portable_color = status_color(portable_status)
    geomag_color = status_color(geomag)

    measure_line = f"HamQSL : {hamqsl_updated}" if hamqsl_updated else "HamQSL : mesure disponible selon source"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="272" viewBox="0 0 1200 272" role="img" aria-label="Propagation HF F4MAJ">
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

  <!-- Badge propagation F4MAJ V1.2 / génération : {svg_escape(generated)} -->

  <rect x="1" y="1" width="1198" height="270" rx="22" fill="url(#bg)" stroke="#334155" stroke-width="2" filter="url(#shadow)"/>

  <text x="28" y="39" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">
    Propagation HF F4MAJ
  </text>

  <text x="28" y="70" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="500" fill="#dbeafe">
    Aperçu indicatif radioamateur — données solaires, géomagnétiques et tendance HF
  </text>

  <text x="842" y="39" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700" fill="#fbbf24">
    {svg_escape(SOURCE_LABEL)}
  </text>

  <text x="842" y="68" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    Mise à jour badge : {svg_escape(generated)}
  </text>

  <rect x="28" y="96" width="174" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="49" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">☀️ SFI</text>
  <text x="48" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{svg_escape(sfi)}</text>

  <rect x="216" y="96" width="174" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="237" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">🧭 Kp</text>
  <text x="236" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{svg_escape(kp)}</text>

  <rect x="404" y="96" width="174" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="425" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">📊 A-index</text>
  <text x="424" y="158" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">{svg_escape(aindex)}</text>

  <rect x="592" y="96" width="174" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="613" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">⚡ X-Ray</text>
  <text x="612" y="158" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="800" fill="#ffffff">{svg_escape(xray_display)}</text>

  <rect x="780" y="96" width="174" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="801" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">🌍 Géomag</text>
  <text x="800" y="158" font-family="Arial, Helvetica, sans-serif" font-size="24" font-weight="800" fill="{geomag_color}">{svg_escape(geomag)}</text>

  <rect x="968" y="96" width="202" height="86" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="990" y="125" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">🕘 Mise à jour</text>
  <text x="990" y="151" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="800" fill="#ffffff">{svg_escape(generated)}</text>
  <text x="990" y="171" font-family="Arial, Helvetica, sans-serif" font-size="11" font-weight="500" fill="#bfdbfe">auto horaire • minute 23</text>

  <rect x="28" y="198" width="360" height="50" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="50" y="222" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">HF générale</text>
  <text x="184" y="222" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="800" fill="{hf_color}">{svg_escape(hf_status)}</text>
  <text x="50" y="241" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="500" fill="#bfdbfe">{svg_escape(hf_note)}</text>

  <rect x="408" y="198" width="360" height="50" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="430" y="222" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">Radio extérieur / Portable</text>
  <text x="640" y="222" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="800" fill="{portable_color}">{svg_escape(portable_status)}</text>
  <text x="430" y="241" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="500" fill="#bfdbfe">{svg_escape(portable_note)}</text>

  <rect x="788" y="198" width="382" height="50" rx="15" fill="url(#card)" stroke="#334155" stroke-width="1.5"/>
  <text x="810" y="222" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" fill="#fbbf24">Mesure source</text>
  <text x="810" y="242" font-family="Arial, Helvetica, sans-serif" font-size="12" font-weight="500" fill="#bfdbfe">{svg_escape(measure_line)}</text>
</svg>
'''


def build_error_svg(message: str) -> str:
    generated = now_fr()
    safe_message = svg_escape(message)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="170" viewBox="0 0 1200 170" role="img" aria-label="Propagation HF F4MAJ indisponible">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>

  <rect x="1" y="1" width="1198" height="168" rx="22" fill="url(#bg)" stroke="#334155" stroke-width="2"/>

  <text x="28" y="42" font-family="Arial, Helvetica, sans-serif" font-size="30" font-weight="800" fill="#ffffff">
    Propagation HF F4MAJ
  </text>

  <text x="28" y="78" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="600" fill="#fbbf24">
    Vérification propagation temporairement indisponible
  </text>

  <text x="28" y="110" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    {safe_message}
  </text>

  <text x="28" y="138" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    Dernier essai : {svg_escape(generated)}
  </text>
</svg>
'''


def main() -> int:
    try:
        data = collect_data()
        svg = build_svg(data)

        print("Propagation data:")
        print(f"SFI: {format_num(data.get('sfi'), 0)}")
        print(f"Kp: {format_num(data.get('kp'), 1)}")
        print(f"A-index: {format_num(data.get('aindex'), 0)}")
        print(f"X-Ray: {data.get('xray')}")
        print(f"HF: {data.get('hf_status')} / {data.get('hf_note')}")
        print(f"Portable: {data.get('portable_status')} / {data.get('portable_note')}")
        print(f"Generated: {data.get('generated')}")
        print(f"HamQSL OK: {data.get('hamqsl_ok')}")
        print(f"NOAA Kp OK: {data.get('noaa_kp_ok')}")
        print(f"NOAA X-Ray OK: {data.get('noaa_xray_ok')}")

    except Exception as exc:
        print(f"Propagation update failed: {exc}")
        svg = build_error_svg(str(exc))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    old_content = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else None

    if old_content == svg:
        print("No propagation badge change.")
        return 0

    OUTPUT_FILE.write_text(svg, encoding="utf-8")
    print(f"Propagation badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
