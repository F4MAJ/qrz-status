#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mise à jour du badge D-STAR F4MAJ pour QRZ.

Objectif :
- détecter si F4MAJ est visible sur la page modules du dashboard XLX933
- détecter le vrai module du réflecteur depuis la colonne du dashboard
- ne pas confondre F4MAJ-B avec le module B
- générer docs/dstar-f4maj.svg
"""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


CALLSIGN = "F4MAJ"

DASHBOARD_URLS = [
    "http://xlx933.hamdigital.fr/index.php?show=mod",
    "https://xlx933.hamdigital.fr/index.php?show=mod",
]

OUTPUT_FILE = Path("docs/dstar-f4maj.svg")


class RowCellParser(HTMLParser):
    """
    Parser volontairement simple :
    - récupère toutes les lignes <tr>
    - récupère les cellules <td> et <th>
    - respecte colspan si présent
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []

        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._current_colspan = 1

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attrs_dict = dict(attrs)

        if tag == "tr":
            self._in_row = True
            self._current_row = []

        elif tag in ("td", "th") and self._in_row:
            self._in_cell = True
            self._current_cell = []

            colspan_raw = attrs_dict.get("colspan", "1")
            try:
                self._current_colspan = max(1, int(colspan_raw))
            except ValueError:
                self._current_colspan = 1

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._in_cell:
            self._current_cell.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._in_cell:
            self._current_cell.append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in ("td", "th") and self._in_cell:
            cell = normalize_text("".join(self._current_cell))

            for _ in range(self._current_colspan):
                self._current_row.append(cell)

            self._current_cell = []
            self._current_colspan = 1
            self._in_cell = False

        elif tag == "tr" and self._in_row:
            if any(cell.strip() for cell in self._current_row):
                self.rows.append(self._current_row)

            self._current_row = []
            self._in_row = False


def fetch_dashboard() -> tuple[str | None, str | None]:
    last_error = None

    for url in DASHBOARD_URLS:
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "F4MAJ-QRZ-DSTAR-Status/1.4",
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


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    return " ".join(value.split())


def html_to_text(source: str) -> str:
    source = re.sub(r"<script[\s\S]*?</script>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<style[\s\S]*?</style>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<[^>]+>", " ", source)
    return normalize_text(source)


def callsign_regex() -> re.Pattern[str]:
    """
    Accepte F4MAJ, F4MAJ-B, F4MAJ-C, F4MAJ-9, etc.
    La lettre après le tiret n'est PAS le module.
    """
    return re.compile(
        r"\b" + re.escape(CALLSIGN) + r"(?:-[A-Z0-9])?\b",
        re.IGNORECASE,
    )


def extract_module_from_header(header_text: str) -> str | None:
    """
    Détecte le module depuis un titre de colonne.

    Exemples :
    - France DSTAR C (57) -> C
    - Europe B (1) -> B
    - France MultiProtocol V (7) -> V
    - XLX933 P -> P
    """
    text = normalize_text(header_text).upper()

    patterns = [
        r"\bFRANCE\s+DSTAR\s+([A-Z])\b",
        r"\bDSTAR\s+([A-Z])\b",
        r"\bD-STAR\s+([A-Z])\b",
        r"\bXLX933\s*([A-Z])\b",
        r"\b([A-Z])\s*\(\d+\)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            letter = match.group(1)
            if len(letter) == 1 and "A" <= letter <= "Z":
                return letter

    return None


def detect_module_from_table_rows(source: str) -> str | None:
    """
    Cherche dans quelle colonne du dashboard se trouve F4MAJ.
    C'est la méthode principale.
    """
    parser = RowCellParser()
    parser.feed(source)

    call_re = callsign_regex()
    current_headers: dict[int, str] = {}

    print("Rows parsed:", len(parser.rows))

    for row_number, row in enumerate(parser.rows, start=1):
        found_header_in_row = False

        for col_index, cell in enumerate(row):
            module = extract_module_from_header(cell)
            if module:
                current_headers[col_index] = module
                found_header_in_row = True

        if found_header_in_row:
            print("Header row:", row_number, current_headers)

        for col_index, cell in enumerate(row):
            if call_re.search(cell):
                print("Callsign found in row:", row_number)
                print("Column:", col_index)
                print("Cell:", cell)
                print("Known headers:", current_headers)

                if col_index in current_headers:
                    return current_headers[col_index]

                # Si le dashboard a un décalage de colonne, on prend l'en-tête le plus proche à gauche.
                left_headers = [
                    (idx, module)
                    for idx, module in current_headers.items()
                    if idx <= col_index
                ]

                if left_headers:
                    return sorted(left_headers, key=lambda item: item[0])[-1][1]

    return None


def detect_module_from_text_sections(source: str) -> str | None:
    """
    Méthode de secours.
    On découpe grossièrement le texte par sections connues.
    """
    text = html_to_text(source)
    call_re = callsign_regex()

    call_match = call_re.search(text)
    if not call_match:
        return None

    call_pos = call_match.start()

    module_patterns = [
        ("B", r"Europe\s+B\s*\(\d+\)"),
        ("C", r"France\s+DSTAR\s+C\s*\(\d+\)"),
        ("D", r"TG208\s+IPSC2FR3\s+D\s*\(\d+\)"),
        ("E", r"Nord\s+Ouest\s+E\s*\(\d+\)"),
        ("M", r"YSF\s+Mayenne\s+M\s*\(\d+\)"),
        ("N", r"NXDN\s+TG933\s+N\s*\(\d+\)"),
        ("V", r"France\s+MultiProtocol\s+V\s*\(\d+\)"),
        ("X", r"X\s*\(\d+\)"),
        ("Y", r"YSF\s+France\s+Y\s*\(\d+\)"),
        ("Z", r"YSF\s+Reunion\s+Z\s*\(\d+\)"),
    ]

    positions: list[tuple[int, str]] = []

    for module, pattern in module_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            positions.append((match.start(), module))

    if not positions:
        return None

    positions.sort()

    selected_module: str | None = None

    for pos, module in positions:
        if pos <= call_pos:
            selected_module = module

    return selected_module


def detect_module(source: str) -> str | None:
    module = detect_module_from_table_rows(source)
    if module:
        return module

    return detect_module_from_text_sections(source)


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
    call_re = callsign_regex()

    if not call_re.search(text):
        return {
            "state": "OFFLINE",
            "module": None,
            "line1": "D-STAR offline",
            "line2": "F4MAJ non visible sur XLX933",
            "detail": "callsign not found",
        }

    module = detect_module(source)

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
