"""Ficha publica de gestores SIN 13F: solo lo que publican ellos o un regulador, con fuente y fecha.

Cada hecho lleva ``label``, ``value``, ``as_of``, ``source_url`` y ``kind``
(``oficial`` = publicado por el gestor/regulador, ``inferido`` = calculado aqui).
Un bloque sin fuente se omite o va a ``None`` con su motivo: nunca se inventa.
"""

from __future__ import annotations

from typing import Any

FACT_KEYS = ("label", "value", "as_of", "source_url", "kind")
KINDS = ("oficial", "inferido")

_WEB = "https://www.numantiapatrimonio.com/"
_LETTER_2025 = "https://www.numantiapatrimonio.com/pdfs/Numantia2025.pdf"
_R4 = "https://www.r4.com/productos-inversion/fondos/fichas/ES0173311103"
_CNMV = "https://www.cnmv.es/portal/consultas/iic/fondo?lang=es&nif=V82363128&vista=2"
_WEB_ASOF = "2026-10-06 (web consultada)"


def _fact(label: str, value: str, as_of: str, source_url: str) -> dict[str, str]:
    return {"label": label, "value": value, "as_of": as_of, "source_url": source_url, "kind": "oficial"}


def _letter(title: str, year: str, path: str) -> dict[str, str]:
    return {"title": title, "date": year, "url": f"{_WEB}pdfs/{path}"}


def _meeting(title: str, year: str, video: str) -> dict[str, str]:
    return {"title": title, "year": year, "url": f"https://www.youtube.com/watch?v={video}"}


PUBLIC_PROFILES: dict[str, dict[str, Any]] = {
    "quintana": {
        "vehicle": {
            "name": "Numantia Patrimonio Global (fondo de inversión)",
            "type": "Fondo de inversión, gestionado por Renta 4 Gestora y asesorado por Emérito Quintana Pelayo EAFN",
            "regulator_id": "ISIN ES0173311103",
            "manager_company": "Renta 4 Gestora",
            "start_date": "2017-07-02",
            "source_url": _WEB,
        },
        "facts": [
            _fact("Rentabilidad desde el inicio (jul 2017)", "+202% tras comisiones", "carta anual 2025", _LETTER_2025),
            _fact("Rentabilidad anual compuesta", "13,6% tras comisiones", "carta anual 2025", _LETTER_2025),
            _fact("Objetivo a largo plazo", "8-12% anual", "carta anual 2025", _LETTER_2025),
            _fact("Empresas en cartera", "25-30 (cartera concentrada)", "carta anual 2025", _LETTER_2025),
            _fact("Comisión de gestión", "1,25% anual", _WEB_ASOF, _WEB),
            _fact("Comisión de depósito", "0,10% anual", _WEB_ASOF, _WEB),
            _fact("Ratio total de gastos (TER)", "1,39%", _WEB_ASOF, _WEB),
            _fact("Comisión de éxito", "0,00%", _WEB_ASOF, _WEB),
            _fact("Aportación mínima", "10 EUR", _WEB_ASOF, _WEB),
            _fact("Valor liquidativo (dato de Renta 4)", "27,84 EUR", "2026-09-30", _R4),
            _fact("Plan de pensiones con la misma cartera", "Numantia Pensiones PP (Rentpensión XVIII FP)", _WEB_ASOF, _WEB),
        ],
        "letters": [
            _letter("Carta anual 2025", "2025", "Numantia2025.pdf"),
            _letter("Carta anual 2024", "2024", "Numantia2024.pdf"),
            _letter("Carta anual 2023", "2023", "Numantia2023.pdf"),
            _letter("Carta anual 2022", "2022", "Numantia2022.pdf"),
            _letter("Carta anual 2021", "2021", "Numantia2021.pdf"),
            _letter("Carta anual 2020", "2020", "Numantia2020.pdf"),
            _letter("4ª carta semestral, marzo 2019", "2019", "Numantia2019.pdf"),
            _letter("3ª carta semestral, agosto 2018", "2018", "Numantia_ago2018.pdf"),
            _letter("2ª carta semestral, febrero 2018", "2018", "Numantia_feb2018.pdf"),
            _letter("1ª carta semestral, agosto 2017", "2017", "Numantia2017.pdf"),
        ],
        "meetings": [
            _meeting("Reunión anual de inversores 2025", "2025", "uhIcWu3gz_E"),
            _meeting("Reunión anual de inversores 2024", "2024", "3HfoCtcsNT0"),
            _meeting("Reunión anual de inversores 2023", "2023", "JW462wqfIkU"),
            _meeting("Reunión anual de inversores 2022", "2022", "ksgelUpRweA"),
            _meeting("Reunión anual de inversores 2021", "2021", "mYCCBchv2yY"),
            _meeting("Reunión anual de inversores 2020", "2020", "v-Kj4Hz4W6I"),
            _meeting("Reunión anual de inversores 2019", "2019", "3Yb_iXfI3GU"),
            _meeting("1ª reunión anual 2018", "2018", "VwG94cGqmJw"),
        ],
        "holdings": None,
        "holdings_note": (
            "Sin datos: la web de Numantia no publica la cartera por posiciones. La CNMV la recoge en los informes "
            "periódicos de R4 Multigestión (enlace en fuentes) y aún no está incorporada."
        ),
        "links": [
            {"label": "Web oficial", "url": _WEB},
            {"label": "Ficha en la CNMV", "url": _CNMV},
            {"label": "Ficha en Renta 4", "url": _R4},
            {"label": "Canal oficial de YouTube", "url": "https://www.youtube.com/@emeritoquintana"},
        ],
    },
}


def public_profile(slug: str) -> dict[str, Any] | None:
    return PUBLIC_PROFILES.get(slug)


def validate_profile(profile: dict[str, Any]) -> list[str]:
    """Problemas de trazabilidad: cada hecho con fuente https, fecha y tipo valido."""
    problems: list[str] = []
    for fact in profile.get("facts", []):
        for key in FACT_KEYS:
            if not str(fact.get(key, "")).strip():
                problems.append(f"{fact.get('label', '?')}: falta {key}")
        if not str(fact.get("source_url", "")).startswith("https://"):
            problems.append(f"{fact.get('label', '?')}: source_url no https")
        if fact.get("kind") not in KINDS:
            problems.append(f"{fact.get('label', '?')}: kind invalido")
    for item in (*profile.get("letters", []), *profile.get("meetings", [])):
        if not str(item.get("url", "")).startswith("https://"):
            problems.append(f"{item.get('title', '?')}: url no https")
    if profile.get("holdings") is None and not str(profile.get("holdings_note", "")).strip():
        problems.append("holdings None sin motivo")
    if not str(profile.get("vehicle", {}).get("source_url", "")).startswith("https://"):
        problems.append("vehicle sin source_url")
    return problems
