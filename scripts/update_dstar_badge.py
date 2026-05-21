#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Badge D-STAR dynamique F4MAJ pour QRZ.

Version V3 :
- détecte F4MAJ / F4MAJ-B sur le dashboard XLX933
- évite de confondre le suffixe radio F4MAJ-B avec le module réflecteur
- évite de prendre le module "Default" XLX933C à la place du vrai "Linked to"
- si une ligne contient plusieurs modules XLX933, priorité au module réellement lié
- génère docs/dstar-f4maj.svg
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional


CALLSIGN = "F4MAJ"
REFLECTOR = "XLX933"

DASHBOARD_URLS = [
    "https://xlx933.hamdigital.fr/index.php?show=liveircddb",
    "http://xlx933.hamdigital.fr/index.php?show=liveircddb",
    "https://xlx933.hamdigital.fr/index.php?show=modules",
    "http://xlx933.hamdigital.fr/index.php?show=modules",
    "https://xlx933.hamdigital.fr/index.php?show=mod",
    "http://xlx933.hamdigital.fr/index.php?show=mod",
]

OUTPUT_FILE = Path("docs/dstar-f4maj.svg")


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\xa0", " ")
    return " ".join(value.split())


def fetch_url(url: str) -> tuple[Optional[str], Optional[str]]:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "F4MAJ-QRZ-DSTAR-Status/3.0",
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
    return re.compile(
        r"\b" + re.escape(CALLSIGN) + r"(?:\s*[- ]\s*[A-Z0-9])?\b",
        re.IGNORECASE,
    )


def row_contains_callsign(row: list[str]) -> bool:
    text = " | ".join(row)
    return callsign_pattern().search(text) is not None


def extract_module(value: str) -> Optional[str]:
    value = normalize_text(value)

    patterns = [
        r"\bXLX\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bXRF\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*033\s*[- ]?\s*([A-Z])\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    return None


def extract_all_modules_from_text(value: str) -> list[str]:
    value = normalize_text(value)
    modules: list[str] = []

    patterns = [
        r"\bXLX\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bXRF\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*933\s*[- ]?\s*([A-Z])\b",
        r"\bDCS\s*033\s*[- ]?\s*([A-Z])\b",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, value, re.IGNORECASE):
            module = match.group(1).upper()
            if module not in modules:
                modules.append(module)

    return modules


def header_index_for_linked_to(header: list[str]) -> Optional[int]:
    for index, cell in enumerate(header):
        cell_lower = cell.lower()
        if "linked" in cell_lower and "to" in cell_lower:
            return index
        if "lié" in cell_lower or "lie" in cell_lower:
            return index
        if "connecté" in cell_lower or "connecte" in cell_lower:
            return index
    return None


def detect_module_from_row_with_header(row: list[str], header: Optional[list[str]]) -> Optional[str]:
    if not header:
        return None

    index = header_index_for_linked_to(header)
    if index is None:
        return None

    if index < len(row):
        module = extract_module(row[index])
        if module:
            return module

    return None


def detect_module_from_cells(row: list[str]) -> Optional[str]:
    """
    Exemple probable d'une ligne live :
    F4MAJ B | XLX933 C | Auto | ... | Up | XLX933 P | ...

    XLX933C peut être le module par défaut.
    XLX933P peut être le vrai module "Linked to".
    Si plusieurs modules sont présents, on privilégie le dernier module détecté,
    car dans ce type de tableau le module linked arrive après le module default.
    """

    cells = [normalize_text(cell) for cell in row]
    modules_by_cell: list[tuple[int, str, str]] = []

    for index, cell in enumerate(cells):
        module = extract_module(cell)
        if module:
            modules_by_cell.append((index, module, cell))

    if not modules_by_cell:
        return None

    # Priorité 1 : cellule située juste après un statut de lien actif.
    for index, cell in enumerate(cells):
        lower = cell.lower()
        if lower in ("up", "linked", "link up", "connected", "connecte", "connecté"):
            if index + 1 < len(cells):
                module = extract_module(cells[index + 1])
                if module:
                    return module

    # Priorité 2 : cellule qui contient explicitement Linked to + module.
    for cell in cells:
        lower = cell.lower()
        if "linked" in lower or "connect" in lower or "lié" in lower or "lie" in lower:
            module = extract_module(cell)
            if module:
                return module

    # Priorité 3 : s'il y a plusieurs modules, prendre le dernier.
    # Cela évite de prendre le module par défaut avant le module réellement lié.
    return modules_by_cell[-1][1]


def detect_from_tables(source: str) -> dict[str, Optional[str]]:
    rows = parse_table_rows(source)
    current_header: Optional[list[str]] = None
    callsign_seen = False

    for row in rows:
        row_lower = " | ".join(row).lower()

        if "linked" in row_lower or "linked to" in row_lower or "connect" in row_lower:
            current_header = row

        if not row_contains_callsign(row):
            continue

        callsign_seen = True
        print("Candidate table row:")
        print(" | ".join(row))

        module = detect_module_from_row_with_header(row, current_header)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "table-header-linked-to",
                "matched": " | ".join(row),
            }

        module = detect_module_from_cells(row)
        if module:
            return {
                "found": "yes",
                "module": module,
                "method": "table-row-last-linked-module",
                "matched": " | ".join(row),
            }

    if callsign_seen:
        return {
            "found": "yes",
            "module": None,
            "method": "table-callsign-found-no-module",
            "matched": None,
        }

    return {
        "found": "no",
        "module": None,
        "method": "table-callsign-not-found",
        "matched": None,
    }


def detect_from_text_lines(source: str) -> dict[str, Optional[str]]:
    lines = strip_html_to_lines(source)
    call_re = callsign_pattern()
    callsign_seen = False

    for line in lines:
        if not call_re.search(line):
            continue

        callsign_seen = True
        print("Candidate text line:")
        print(line)

        linked_match = re.search(
            r"(linked\s*to|connect(?:ed|e|é)?\s*(?:to|a|à)?|lié\s*à|lie\s*a).{0,120}",
            line,
            re.IGNORECASE,
        )

        if linked_match:
            module = extract_module(linked_match.group(0))
            if module:
                return {
                    "found": "yes",
                    "module": module,
                    "method": "text-explicit-linked-to",
                    "matched": line,
                }

        modules = extract_all_modules_from_text(line)
        if modules:
            return {
                "found": "yes",
                "module": modules[-1],
                "method": "text-last-module",
                "matched": line,
            }

    if callsign_seen:
        return {
            "found": "yes",
            "module": None,
            "method": "text-callsign-found-no-module",
            "matched": None,
        }

    return {
        "found": "no",
        "module": None,
        "method": "text-callsign-not-found",
        "matched": None,
    }


def detect_from_source(source: str) -> dict[str, Optional[str]]:
    table_detection = detect_from_tables(source)

    if table_detection.get("found") == "yes" and table_detection.get("module"):
        return table_detection

    text_detection = detect_from_text_lines(source)

    if text_detection.get("found") == "yes":
        return text_detection

    return table_detection


def get_status() -> dict[str, Optional[str]]:
    errors: list[str] = []
    callsign_seen = False
    last_method = ""
    last_match = ""

    for url in DASHBOARD_URLS:
        print(f"Checking: {url}")
        source, error = fetch_url(url)

        if source is None:
            errors.append(error or f"{url} -> unknown error")
            print(f"Fetch failed: {error}")
            continue

        detection = detect_from_source(source)

        print(f"Detection method: {detection.get('method')}")
        print(f"Detected module: {detection.get('module') or '-'}")

        if detection.get("found") == "yes":
            callsign_seen = True
            last_method = detection.get("method") or ""
            last_match = detection.get("matched") or ""

            module = detection.get("module")
            if module:
                return {
                    "state": "ONLINE",
                    "module": module,
                    "line1": "D-STAR online",
                    "line2": f"{CALLSIGN} visible sur {REFLECTOR}{module}",
                    "detail": f"{url} / {detection.get('method')}",
                }

    if callsign_seen:
        return {
            "state": "ONLINE",
            "module": None,
            "line1": "D-STAR online",
            "line2": f"{CALLSIGN} visible sur {REFLECTOR}",
            "detail": f"{last_method} / {last_match}",
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
        "line2": f"{CALLSIGN} non visible sur {REFLECTOR}",
        "detail": "callsign not found",
    }


def svg_escape(value: Optional[str]) -> str:
    return html.escape(value or "", quote=True)


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

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="608" height="118" viewBox="0 0 608 118" role="img" aria-label="D-STAR F4MAJ status">
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

  <rect x="1" y="1" width="606" height="116" rx="18" fill="url(#bg)" stroke="#334155" stroke-width="2"/>

  <circle cx="52" cy="59" r="16" fill="{main_color}" filter="url(#softGlow)"/>
  <circle cx="52" cy="59" r="7" fill="{glow_color}"/>

  <text x="86" y="38" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="700" fill="#ffffff">
    D-STAR F4MAJ
  </text>

  <text x="86" y="66" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="500" fill="#e5e7eb">
    {line1} — {line2}
  </text>

  <text x="86" y="92" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="700" fill="#fbbf24">
    Dashboard XLX933 · badge QRZ automatique
  </text>

  <text x="520" y="38" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="500" fill="#bfdbfe">
    {state_label}
  </text>
</svg>
"""


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
        print("No badge change.")
        return 0

    OUTPUT_FILE.write_text(svg, encoding="utf-8")
    print(f"Badge updated: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
