#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Mise à jour du badge D-STAR F4MAJ pour QRZ.

Objectif :
- détecter si F4MAJ est visible sur la page modules du dashboard XLX933
- détecter le vrai module du réflecteur depuis les compteurs du dashboard
- ne pas confondre F4MAJ-B avec le module B
- générer docs/dstar-f4maj.svg
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
                    "User-Agent": "F4MAJ-QRZ-DSTAR-Status/1.5",
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
    source = re.sub(r"<br\s*/?>", " ", source, flags=re.IGNORECASE)
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


def find_module_headers(text: str) -> list[tuple[str, int, int]]:
    """
    Lit les en-têtes de modules dans le texte du dashboard.

    Exemples attendus :
    Europe B (1)
    France DSTAR C (57)
    TG208 IPSC2FR3 D (3)
    Nord Ouest E (1)
    YSF Mayenne M (3)
    NXDN TG933 N (5)
    France MultiProtocol V (7)
    X (4)
    YSF France Y (3)
    YSF Reunion Z (1)
    """
    header_matches: list[tuple[str, int, int]] = []

    # On prend les lettres de modules qui apparaissent sous la forme X (nombre).
    # Cela évite de confondre F4MAJ-B avec un module.
    for match in re.finditer(r"\b([A-Z])\s*\((\d+)\)", text):
        letter = match.group(1)
        count = int(match.group(2))

        # On ignore les compteurs trop grands ou inutiles qui ne sont pas des modules actifs.
        if 0 <= count <= 200:
            header_matches.append((letter, count, match.start()))

    # Nettoyage simple : on garde l'ordre et on évite les doublons consécutifs.
    cleaned: list[tuple[str, int, int]] = []
    seen_positions: set[tuple[str, int]] = set()

    for letter, count, pos in header_matches:
        key = (letter, pos)
        if key not in seen_positions:
            cleaned.append((letter, count, pos))
            seen_positions.add(key)

    return cleaned


def find_callsign_entries_after_headers(text: str, start_position: int, expected_total: int) -> list[str]:
    """
    Récupère les indicatifs du dashboard après les en-têtes de modules.
    """
    search_area = text[start_position:]

    # Indicatif avec suffixe D-STAR : F4MAJ-B, F5ABC-C, ON0XXX-B, etc.
    entry_re = re.compile(r"\b[A-Z0-9]{2,12}-[A-Z0-9]\b", re.IGNORECASE)

    entries = [match.group(0).upper() for match in entry_re.finditer(search_area)]

    if expected_total > 0:
        return entries[:expected_total]

    return entries


def detect_module_by_counts(text: str) -> str | None:
    """
    Méthode principale.

    Le dashboard XLX933 est rendu de manière difficile à lire automatiquement.
    On utilise donc les compteurs des modules :
    B(1), C(57), D(3), etc.
    Puis on cherche à quelle tranche appartient F4MAJ-B.
    """
    headers = find_module_headers(text)

    if not headers:
        print("No module headers found.")
        return None

    print("Module headers:", headers)

    # On évite de prendre des compteurs du menu avant la vraie zone modules.
    # La bonne zone commence au premier module détecté.
    first_header_pos = headers[0][2]
    last_header_pos = headers[-1][2]

    total_users = sum(count for _, count, _ in headers)
    entries = find_callsign_entries_after_headers(text, last_header_pos, total_users)

    print("Expected users from headers:", total_users)
    print("Parsed user entries:", len(entries))

    call_re = callsign_regex()

    found_index: int | None = None

    for index, entry in enumerate(entries):
        if call_re.search(entry):
            found_index = index
            print("Callsign entry found:", entry)
            print("Callsign index:", found_index)
            break

    if found_index is None:
        return None

    cursor = 0

    for module, count, _ in headers:
        start = cursor
        end = cursor + count

        print(f"Module {module}: entries {start} to {end - 1}")

        if start <= found_index < end:
            return module

        cursor = end

    return None


def detect_module_from_nearby_headers(text: str) -> str | None:
    """
    Méthode de secours.
    Si le découpage par compteur échoue, on regarde le dernier module connu avant l'indicatif.
    """
    call_match = callsign_regex().search(text)
    if not call_match:
        return None

    call_pos = call_match.start()
    headers = find_module_headers(text)

    selected: str | None = None

    for module, _count, pos in headers:
        if pos <= call_pos:
            selected = module

    return selected


def detect_module(text: str) -> str | None:
    module = detect_module_by_counts(text)
    if module:
        return module

    return detect_module_from_nearby_headers(text)


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
