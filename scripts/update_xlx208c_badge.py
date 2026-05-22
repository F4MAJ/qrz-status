#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Badge dynamique XLX208C F4MAJ pour QRZ.

But :
- vérifier si F4MAJ / F4MAJ-B est visible sur XLX208C
- générer docs/xlx208c-f4maj.svg
- ne pas toucher au badge XLX933 existant
- ne pas toucher à la page QRZ
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo


CALLSIGN = "F4MAJ"
REFLECTOR = "XLX208"
MODULE = "C"
TIMEZONE = "Europe/Paris"

OUTPUT_FILE = Path("docs/xlx208c-f4maj.svg")

# Plusieurs chemins sont testés pour maximiser les chances de lecture du dashboard.
SOURCES = [
    {
        "name": "users-pgs-module-C",
        "url": "https://xlx208.f5kav.fr/users/pgs/users.php?module=C",
        "assume_module": "C",
    },
    {
        "name": "repeaters-pgs-module-C",
        "url": "https://xlx208.f5kav.fr/users/pgs/repeaters.php?module=C",
        "assume_module": "C",
    },
    {
        "name": "root-users-pgs-module-C",
        "url": "https://xlx208.f5kav.fr/pgs/users.php?module=C",
        "assume_module": "C",
    },
    {
        "name": "root-repeaters-pgs-module-C",
        "url": "https://xlx208.f5kav.fr/pgs/repeaters.php?module=C",
        "assume_module": "C",
    },
    {
        "name": "dashboard-users",
        "url": "https://xlx208.f5kav.fr/users/index.php?show=users&module=C",
        "assume_module": "C",
    },
    {
        "name": "dashboard-repeaters",
        "url": "https://xlx208.f5kav.fr/users/index.php?show=repeaters&module=C",
        "assume_module": "C",
    },
    {
        "name": "dashboard-public",
        "url": "https://xlx208.f5kav.fr/users/C",
        "assume_module": "C",
    },
]


def now_fr() -> str:
    return datetime.now(ZoneInfo(TIMEZONE)).strftime("%d/%m/%Y %H:%M")


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    return " ".join(value.split())


def svg_escape(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def fetch_url(url: str) -> tuple[Optional[str], Optional[str]]:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "F4MAJ-QRZ-XLX208C-Status/1.0",
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
        return None, str(exc)


class TableRowParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.in_row = False
        self.in_cell = False
        self.current_row: list[str] = []
        self.current_cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()

        if tag == "tr":
            self.in_row = True
            self.current_row = []

        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell_parts = []

        elif tag == "br" and self.in_cell:
            self.current_cell_parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in ("td", "th") and self.in_cell:
            cell = normalize_text(" ".join(self.current_cell_parts))
            self.current_row.append(cell)
            self.current_cell_parts = []
            self.in_cell = False

        elif tag == "tr" and self.in_row:
            cleaned = [normalize_text(cell) for cell in self.current_row if normalize_text(cell)]
            if cleaned:
                self.rows.append(cleaned)
            self.current_row = []
            self.in_row = False


def parse_table_rows(source: str) -> list[list[str]]:
    parser = TableRowParser()
    parser.feed(source)
    return parser.rows


def strip_html_to_lines(source: str) -> list[str]:
    source = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", source)
    source = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", source)
    source = re.sub(r"(?i)<br\s*/?>", "\n", source)
    source = re.sub(r"(?i)</\s*(td|th)\s*>", " | ", source)
    source = re.sub(r"(?i)</\s*tr\s*>", "\n", source)
    source = re.sub(r"<[^>]+>", " ", source)
    source = html.unescape(source)

    lines = []
    for raw_line in source.splitlines():
        line = normalize_text(raw_line)
        if line:
            lines.append(line)

    return lines


def callsign_pattern() -> re.Pattern[str]:
    # Accepte F4MAJ, F4MAJ-B, F4MAJ B, F4MAJ-10, etc.
    return re.compile(
        r"\b" + re.escape(CALLSIGN) + r"(?:\s*[- ]\s*[A-Z0-9]+)?\b",
        re.IGNORECASE,
    )


def row_contains_callsign(row: list[str]) -> bool:
    return callsign_pattern().search(" | ".join(row)) is not None


def extract_module_from_text(value: str) -> Optional[str]:
    value = normalize_text(value)

    patterns = [
        r"\bXLX\s*208\s*[- ]?\s*([A-Z])\b",
        r"\bXRF\s*208\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*208\s*[- ]?\s*([A-Z])\b",
        r"\bmodule\s+([A-Z])\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    # Cas cellule Module contenant uniquement C.
    if re.fullmatch(r"[A-Z]", value.strip(), re.IGNORECASE):
        return value.strip().upper()

    return None


def is_probable_header(row: list[str]) -> bool:
    text = " | ".join(row).lower()
    keywords = [
        "dv station",
        "station",
        "last heard",
        "linked",
        "protocol",
        "module",
        "ip",
        "band",
        "flag",
        "repeater",
        "node",
    ]
    return sum(1 for keyword in keywords if keyword in text) >= 2


def find_header_index(header: list[str], accepted_names: list[str]) -> Optional[int]:
    for index, cell in enumerate(header):
        cell_lower = cell.lower()
        for name in accepted_names:
            if name in cell_lower:
                return index
    return None


def detect_module_with_header(row: list[str], header: Optional[list[str]]) -> Optional[str]:
    if not header:
        return None

    module_index = find_header_index(header, ["module"])
    if module_index is not None and module_index < len(row):
        module = extract_module_from_text(row[module_index])
        if module:
            return module

    linked_index = find_header_index(header, ["linked", "lié", "connect"])
    if linked_index is not None and linked_index < len(row):
        module = extract_module_from_text(row[linked_index])
        if module:
            return module

    return None


def detect_from_tables(source: str, assume_module: Optional[str]) -> dict[str, Optional[str]]:
    rows = parse_table_rows(source)
    header: Optional[list[str]] = None

    for row in rows:
        if is_probable_header(row):
            header = row
            print("Header row:")
            print(" | ".join(row))
            continue

        if not row_contains_callsign(row):
            continue

        row_text = " | ".join(row)
        print("Candidate table row:")
        print(row_text)

        module = detect_module_with_header(row, header)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "table-header-module",
                "matched": row_text,
            }

        # Si la source est déjà filtrée sur le module C, on peut conclure C.
        if assume_module:
            return {
                "found": "yes",
                "module": assume_module,
                "method": "assumed-module-from-filtered-source",
                "matched": row_text,
            }

        return {
            "found": "yes",
            "module": None,
            "method": "table-callsign-found-no-module",
            "matched": row_text,
        }

    return {
        "found": "no",
        "module": None,
        "method": "table-callsign-not-found",
        "matched": None,
    }


def detect_from_text(source: str, assume_module: Optional[str]) -> dict[str, Optional[str]]:
    call_re = callsign_pattern()

    for line in strip_html_to_lines(source):
        if not call_re.search(line):
            continue

        print("Candidate text line:")
        print(line)

        module = extract_module_from_text(line)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "text-module",
                "matched": line,
            }

        if assume_module:
            return {
                "found": "yes",
                "module": assume_module,
                "method": "text-assumed-module-from-filtered-source",
                "matched": line,
            }

        return {
            "found": "yes",
            "module": None,
            "method": "text-callsign-found-no-module",
            "matched": line,
        }

    return {
        "found": "no",
        "module": None,
        "method": "text-callsign-not-found",
        "matched": None,
    }


def detect_from_source(source: str, assume_module: Optional[str]) -> dict[str, Optional[str]]:
    table_detection = detect_from_tables(source, assume_module)

    if table_detection.get("found") == "yes":
        return table_detection

    return detect_from_text(source, assume_module)


def get_status() -> dict[str, Optional[str]]:
    errors: list[str] = []

    for source in SOURCES:
        name = source["name"]
        url = source["url"]
        assume_module = source["assume_module"]

        print(f"Checking source: {name}")
        print(f"URL: {url}")

        html_source, error = fetch_url(url)

        if html_source is None:
            errors.append(f"{name}: {error}")
            print(f"Fetch failed: {error}")
            continue

        detection = detect_from_source(html_source, assume_module)

        print(f"Detection method: {detection.get('method')}")
        print(f"Detected module: {detection.get('module') or '-'}")

        if detection.get("found") != "yes":
            continue

        module = detection.get("module")

        if module == MODULE:
            return {
                "state": "ONLINE",
                "module": module,
                "line1": "XLX208C online",
                "line2": f"{CALLSIGN} visible sur {REFLECTOR}{MODULE}",
                "detail": f"{name} / {detection.get('method')}",
            }

        if module:
            return {
                "state": "ONLINE_OTHER_MODULE",
                "module": module,
                "line1": "XLX208 online",
                "line2": f"{CALLSIGN} visible sur {REFLECTOR}{module}",
                "detail": f"{name} / {detection.get('method')}",
            }

        return {
            "state": "ONLINE",
            "module": None,
            "line1": "XLX208 online",
            "line2": f"{CALLSIGN} visible sur {REFLECTOR}",
            "detail": f"{name} / {detection.get('method')}",
        }

    if errors and len(errors) == len(SOURCES):
        return {
            "state": "UNKNOWN",
            "module": None,
            "line1": "Vérification impossible",
            "line2": "Dashboard XLX208 non accessible",
            "detail": " | ".join(errors),
        }

    return {
        "state": "OFFLINE",
        "module": None,
        "line1": "XLX208C offline",
        "line2": f"{CALLSIGN} non visible sur {REFLECTOR}{MODULE}",
        "detail": "callsign not found",
    }


def build_svg(status: dict[str, Optional[str]]) -> str:
    state = status.get("state") or "UNKNOWN"

    if state == "ONLINE":
        main_color = "#22c55e"
        glow_color = "#86efac"
        state_label = "ONLINE"
    elif state == "ONLINE_OTHER_MODULE":
        main_color = "#38bdf8"
        glow_color = "#bae6fd"
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
    generated = svg_escape(now_fr())

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="608" height="118" viewBox="0 0 608 118" role="img" aria-label="XLX208C F4MAJ status">
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

  <!-- Badge XLX208C F4MAJ / génération : {generated} -->

  <rect x="1" y="1" width="606" height="116" rx="18" fill="url(#bg)" stroke="#334155" stroke-width="2"/>

  <circle cx="52" cy="59" r="16" fill="{main_color}" filter="url(#softGlow)"/>
  <circle cx="52" cy="59" r="7" fill="{glow_color}"/>

  <text x="86" y="38" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="700" fill="#ffffff">
    XLX208C F4MAJ
  </text>

  <text x="86" y="66" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="500" fill="#e5e7eb">
    {line1} — {line2}
  </text>

  <text x="86" y="92" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="700" fill="#fbbf24">
    Dashboard XLX208C · badge QRZ automatique
  </text>

  <text x="520" y="38" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    {state_label}
  </text>
</svg>
'''


def main() -> int:
    status = get_status()

    print("Final status:")
    print(f"State: {status.get('state')}")
    print(f"Module: {status.get('module') or '-'}")
    print(f"Detail: {status.get('detail') or '-'}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    svg = build_svg(status)
    old_content = OUTPUT_FILE.read_text(encoding="utf-8") if OUTPUT_FILE.exists() else None

    if old_content == svg:
        print("No XLX208C badge change.")
        return 0

    OUTPUT_FILE.write_text(svg, encoding="utf-8")
    print(f"XLX208C badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
