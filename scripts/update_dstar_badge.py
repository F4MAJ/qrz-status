#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mise à jour du badge D-STAR F4MAJ pour QRZ.

Le script vérifie le dashboard XLX933 et génère :
docs/dstar-f4maj.svg
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from pathlib import Path


CALLSIGN = "F4MAJ"

DASHBOARD_URLS = [
    "http://xlx933.hamdigital.fr/index.php?show=mod",
    "https://xlx933.hamdigital.fr/index.php?show=mod",
]

OUTPUT_FILE = Path("docs/dstar-f4maj.svg")


def fetch_dashboard() -> tuple[str | None, str | None]:
    last_error = None

    for url in DASHBOARD_URLS:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "F4MAJ-QRZ-DSTAR-Status/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )

            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace"), None

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = f"{url} -> {exc}"

    return None, last_error


def html_to_text(source: str) -> str:
    source = re.sub(r"<script[\s\S]*?</script>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<style[\s\S]*?</style>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<[^>]+>", " ", source)
    source = html.unescape(source)
    return " ".join(source.split())


def detect_module(text: str) -> str | None:
    upper = text.upper()
    callsign = CALLSIGN.upper()

    idx = upper.find(callsign)
    if idx < 0:
        return None

    window = text[max(0, idx - 500): idx + 900]
    window_upper = window.upper()

    patterns = [
        r"XLX933\s*[- ]?\s*([A-Z])\b",
        r"MODULE\s*[:\- ]\s*([A-Z])\b",
        r"MOD\s*[:\- ]\s*([A-Z])\b",
        r"\b([A-Z])\s+" + re.escape(callsign) + r"\b",
        re.escape(callsign) + r"\s+([A-Z])\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, window_upper)
        if match:
            letter = match.group(1)
            if len(letter) == 1 and "A" <= letter <= "Z":
                return letter

    return None


def get_status() -> dict[str, str | None]:
    source, error = fetch_dashboard()

    if source is None:
        return {
            "state": "UNKNOWN",
            "module": None,
            "line1": "Vérification impossible",
            "line2": "Dashboard XLX933 non accessible",
            "detail": error or "unknown error",
        }

    text = html_to_text(source)
    upper = text.upper()

    if CALLSIGN.upper() not in upper:
        return {
            "state": "OFFLINE",
            "module": None,
            "line1": "D-STAR offline",
            "line2": "F4MAJ non visible sur XLX933",
            "detail": "callsign not found",
        }

    module = detect_module(text)

    if module:
        return {
            "state": "ONLINE",
            "module": module,
            "line1": "D-STAR online",
            "line2": f"F4MAJ visible sur XLX933{module}",
            "detail": f"module {module}",
        }

    return {
        "state": "ONLINE",
        "module": None,
        "line1": "D-STAR online",
        "line2": "F4MAJ visible sur XLX933",
        "detail": "module not detected",
    }


def svg_escape(value: str | None) -> str:
    if value is None:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_svg(status: dict[str, str | None]) -> str:
    state = status["state"]

    if state == "ONLINE":
        main_color = "#22c55e"
        glow_color = "#86efac"
        state_label = "ONLINE"
    elif state == "OFFLINE":
        main_color = "#ef4444"
        glow_color = "#fca5a5"
        state_label = "OFFLINE"
    else:
        main_color = "#f59e0b"
        glow_color = "#fde68a"
        state_label = "UNKNOWN"

    line1 = svg_escape(status["line1"])
    line2 = svg_escape(status["line2"])

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="620" height="130" viewBox="0 0 620 130">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#172033"/>
      <stop offset="70%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1f2937"/>
    </linearGradient>

    <filter id="shadow" x="-10%" y="-10%" width="120%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="8" flood-color="#000000" flood-opacity="0.32"/>
    </filter>
  </defs>

  <rect x="8" y="8" width="604" height="114" rx="20" fill="url(#bg)" stroke="#334155" stroke-width="2" filter="url(#shadow)"/>

  <circle cx="58" cy="65" r="17" fill="{main_color}"/>
  <circle cx="58" cy="65" r="8" fill="{glow_color}"/>

  <text x="92" y="43" font-family="Arial, Helvetica, sans-serif" font-size="23" font-weight="700" fill="#ffffff">
    D-STAR F4MAJ
  </text>

  <text x="92" y="73" font-family="Arial, Helvetica, sans-serif" font-size="17" fill="#d1d5db">
    {line1} — {line2}
  </text>

  <text x="92" y="98" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#fbbf24">
    Dashboard XLX933 • badge QRZ automatique
  </text>

  <text x="500" y="43" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#94a3b8">
    {state_label}
  </text>
</svg>
'''


def main() -> int:
    status = get_status()

    print(f"Detected state: {status['state']}")
    print(f"Detected module: {status.get('module') or '-'}")
    print(f"Detail: {status.get('detail') or '-'}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    svg = build_svg(status)
    old_content = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else None

    if old_content == svg:
        print("No badge change.")
        return 0

    OUTPUT_FILE.write_text(svg, encoding="utf-8")
    print(f"Badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
