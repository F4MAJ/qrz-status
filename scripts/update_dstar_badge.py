#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mise à jour du badge D-STAR F4MAJ pour QRZ.

Objectif V2 :
- lire en priorité la page D-Star live / ircDDB du dashboard XLX933
- détecter la ligne contenant F4MAJ / F4MAJ-B
- lire le vrai champ "Linked to XLX933 X"
- ne plus confondre le suffixe radio F4MAJ-B avec le module du réflecteur
- éviter d'afficher XLX933C si le hotspot est réellement linked to XLX933P
- générer docs/dstar-f4maj.svg
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


CALLSIGN = "F4MAJ"

# Priorité aux pages qui peuvent contenir la vraie information "Linked to".
DASHBOARD_URLS = [
    "https://xlx933.hamdigital.fr/index.php?show=liveircddb",
    "http://xlx933.hamdigital.fr/index.php?show=liveircddb",
    "https://xlx933.hamdigital.fr/index.php?show=mod",
    "http://xlx933.hamdigital.fr/index.php?show=mod",
]

OUTPUT_FILE = Path("docs/dstar-f4maj.svg")


def fetch_url(url: str) -> tuple[Optional[str], Optional[str]]:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "F4MAJ-QRZ-DSTAR-Status/2.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )

        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace"), None

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        return None, f"{url} -> {exc}"


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    return " ".join(value.split())


def strip_html_tags(source: str) -> str:
    source = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", source)
    source = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", source)
    source = re.sub(r"(?i)<br\s*/?>", "\n", source)
    source = re.sub(r"(?i)</\s*(td|th)\s*>", " | ", source)
    source = re.sub(r"(?i)</\s*tr\s*>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    return html.unescape(source)


def html_to_lines(source: str) -> list[str]:
    text = strip_html_tags(source)
    lines = []

    for raw_line in text.splitlines():
        line = normalize_text(raw_line)
        if line:
            lines.append(line)

    return lines


def html_to_text(source: str) -> str:
    return normalize_text(strip_html_tags(source))


def callsign_regex() -> re.Pattern[str]:
    """
    Accepte :
    - F4MAJ
    - F4MAJ-B
    - F4MAJ B

    Attention :
    la lettre B dans F4MAJ-B est le suffixe D-STAR du poste/hotspot,
    ce n'est pas le module du réflecteur.
    """
    return re.compile(
        r"\b" + re.escape(CALLSIGN) + r"(?:\s*[- ]\s*[A-Z0-9])?\b",
        re.IGNORECASE,
    )


def extract_linked_module_from_text(text: str) -> Optional[str]:
    """
    Cherche uniquement après une indication de type :
    Linked to XLX933 P
    Linked to : XLX933P
    Linked to XLX 933 P

    On évite volontairement de prendre le premier XLX933 trouvé dans la ligne,
    car une ligne peut contenir :
    F4MAJ B | XLX933 C | ... | Linked to XLX933 P
    Dans ce cas le vrai module actif est P, pas C.
    """

    anchor_match = re.search(
        r"(linked\s*to|link\s*to|lié\s*à|lie\s*a|connecté\s*à|connecte\s*a)",
        text,
        re.IGNORECASE,
    )

    if not anchor_match:
        return None

    search_area = text[anchor_match.start():]

    patterns = [
        r"\bXLX\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bXRF\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*033\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*933\s*[- ]?\s*([A-Z])\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, search_area, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def find_callsign_rows(lines: list[str]) -> list[str]:
    call_re = callsign_regex()
    return [line for line in lines if call_re.search(line)]


def detect_from_linked_rows(source: str) -> dict[str, Optional[str]]:
    lines = html_to_lines(source)
    rows = find_callsign_rows(lines)

    for row in rows:
        module = extract_linked_module_from_text(row)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "linked-row",
                "matched_row": row,
            }

    # Secours : parfois le texte HTML aplati garde F4MAJ et Linked to proches,
    # mais pas forcément sur la même ligne.
    full_text = html_to_text(source)
    call_re = callsign_regex()
    call_match = call_re.search(full_text)

    if call_match:
        start = max(0, call_match.start() - 250)
        end = min(len(full_text), call_match.end() + 500)
        nearby_text = full_text[start:end]

        module = extract_linked_module_from_text(nearby_text)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "linked-nearby-text",
                "matched_row": nearby_text,
            }

        return {
            "found": "yes",
            "module": None,
            "method": "callsign-found-no-linked-module",
            "matched_row": nearby_text,
        }

    return {
        "found": "no",
        "module": None,
        "method": "callsign-not-found",
        "matched_row": None,
    }


def get_status() -> dict[str, Optional[str]]:
    errors = []
    callsign_seen = False
    fallback_detail = None

    for url in DASHBOARD_URLS:
        print(f"Checking: {url}")
        source, error = fetch_url(url)

        if source is None:
            errors.append(error or f"{url} -> unknown error")
            print(f"Fetch failed: {error}")
            continue

        detection = detect_from_linked_rows(source)
        print(f"Detection method: {detection.get('method')}")
        print(f"Detected module: {detection.get('module') or '-'}")

        if detection.get("found") == "yes":
            callsign_seen = True
            fallback_detail = detection.get("matched_row")

            module = detection.get("module")
            if module:
                return {
                    "state": "ONLINE",
                    "module": module,
                    "line1": "D-STAR online",
                    "line2": f"{CALLSIGN} visible sur XLX933{module}",
                    "detail": f"{url} / {detection.get('method')}",
                }

    if callsign_seen:
        return {
            "state": "ONLINE",
            "module": None,
            "line1": "D-STAR online",
            "line2": f"{CALLSIGN} visible sur XLX933",
            "detail": fallback_detail or "callsign found but linked module not detected",
        }

    if errors and len(errors) == len(DASHBOARD_URLS):
        return {
            "state": "UNKNOWN",
            "module": None,
            "line1": "Vérification impossible",
            "line2": "Dashboard XLX933 non accessible",
            "detail": " | ".join(errors),
        }

    return {
        "state": "OFFLINE",
        "module": None,
        "line1": "D-STAR offline",
        "line2": f"{CALLSIGN} non visible sur XLX933",
        "detail": "callsign not found",
    }


def svg_escape(value: Optional[str]) -> str:
    if value is None:
        return ""
    return html.escape(value, quote=True)


def build_svg(status: dict[str, Optional[str]]) -> str:
    state = status.get("state") or "UNKNOWN"

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

    line1 = svg_escape(status.get("line1"))
    line2 = svg_escape(status.get("line2"))

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="92" viewBox="0 0 1000 92" role="img" aria-label="D-STAR F4MAJ status">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>

  <rect x="1" y="1" width="998" height="90" rx="18" fill="url(#bg)" stroke="#334155" stroke-width="2"/>

  <circle cx="42" cy="46" r="10" fill="{main_color}" filter="url(#softGlow)"/>
  <circle cx="42" cy="46" r="4" fill="{glow_color}"/>

  <text x="70" y="34" font-family="Arial, Helvetica, sans-serif" font-size="24" font-weight="700" fill="#ffffff">
    D-STAR F4MAJ
  </text>

  <text x="70" y="62" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="600" fill="#cbd5e1">
    {line1} — {line2}
  </text>

  <rect x="820" y="24" width="145" height="44" rx="12" fill="{main_color}" opacity="0.16" stroke="{main_color}" stroke-width="1.5"/>

  <text x="892" y="53" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="{main_color}">
    {state_label}
  </text>
</svg>
"""


def main() -> int:
    status = get_status()

    print(f"Detected state: {status.get('state')}")
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
