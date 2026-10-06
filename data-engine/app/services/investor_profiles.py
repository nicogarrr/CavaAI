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
            _fact("Rentabilidad desde el inicio (jul 2017)", "+202% tras comisiones", "carta anual 2025 (publicada en 2026)", _LETTER_2025),
            _fact("Rentabilidad anual compuesta", "13,6% tras comisiones", "carta anual 2025 (publicada en 2026)", _LETTER_2025),
            _fact("Objetivo a largo plazo", "8-12% anual", "carta anual 2025 (publicada en 2026)", _LETTER_2025),
            _fact("Empresas en cartera", "25-30 (cartera concentrada)", "carta anual 2025 (publicada en 2026)", _LETTER_2025),
            _fact("Comisión de gestión", "1,25% anual", _WEB_ASOF, _WEB),
            _fact("Comisión de depósito", "0,10% anual", _WEB_ASOF, _WEB),
            _fact("Ratio total de gastos (TER)", "1,39%", _WEB_ASOF, _WEB),
            _fact("Comisión de éxito", "0,00%", _WEB_ASOF, _WEB),
            _fact("Aportación mínima", "10 EUR", _WEB_ASOF, _WEB),
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


_WEB_ASOF_GENERIC = "2026-10-06 (web consultada)"

_CSU_RELEASE = "https://www.csisoftware.com/constellation-software-releases-letter-to-shareholders/"
_CSU_WEB = "https://www.csisoftware.com/"
_AMZN_LETTERS = "https://www.aboutamazon.com/about-us/shareholder-letters"
_AMZN_1997 = "https://s2.q4cdn.com/299287126/files/doc_financials/annual/Shareholderletter97.pdf"
_AMZN_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1018724&type=10-K"
_BRK_LETTERS = "https://www.berkshirehathaway.com/letters/letters.html"
_BRK_2023 = "https://www.berkshirehathaway.com/letters/2023ltr.pdf"
_BRK_NEWS = "https://www.berkshirehathaway.com/news/nov2823.pdf"
_NOMAD = "https://igyfoundation.org.uk/wp-content/uploads/2021/03/Full_Collection_Nomad_Letters.pdf"

PUBLIC_PROFILES["mark-leonard"] = {
    "vehicle": {
        "name": "Constellation Software Inc. (TSX: CSU)",
        "type": "Empresa cotizada que adquiere, gestiona y construye negocios de software de mercado vertical; Mark Leonard firma como Presidente (comunicado del 15 feb 2021)",
        "regulator_id": "TSX: CSU",
        "manager_company": "Constellation Software Inc.",
        "start_date": "",
        "source_url": _CSU_RELEASE,
    },
    "facts": [
        _fact("Actividad", "Adquiere, gestiona y construye negocios de software de mercado vertical", "2021-02-15", _CSU_RELEASE),
        _fact("Clientes", "Más de 150.000 en más de 160 países", _WEB_ASOF_GENERIC, _CSU_WEB),
        _fact("Enfoque", "Adquisiciones de compra y mantenimiento a largo plazo; las filiales operan con autonomía", _WEB_ASOF_GENERIC, _CSU_WEB),
    ],
    "letters": [
        {"title": "Comunicado de la carta a los accionistas de Mark Leonard (15 feb 2021)", "date": "2021", "url": _CSU_RELEASE},
    ],
    "meetings": [],
    "holdings": None,
    "holdings_note": (
        "Sin datos: Mark Leonard no presenta 13F y no hay una fuente pública incorporada con su cartera personal. "
        "Los informes a accionistas de Constellation están en su web."
    ),
    "links": [
        {"label": "Web oficial de Constellation", "url": _CSU_WEB},
    ],
}

PUBLIC_PROFILES["bezos"] = {
    "vehicle": {
        "name": "Amazon.com, Inc.",
        "type": "Empresa cotizada fundada por Jeff Bezos; su carta de 1997 a los accionistas está firmada por Jeffrey P. Bezos",
        "regulator_id": "SEC CIK 0001018724",
        "manager_company": "Amazon.com, Inc.",
        "start_date": "",
        "source_url": _AMZN_1997,
    },
    "facts": [
        _fact("Clientes servidos a cierre de 1997", "Más de 1,5 millones", "carta a los accionistas de 1997", _AMZN_1997),
        _fact("Crecimiento de ingresos en 1997", "+838% hasta 147,8 M$", "carta a los accionistas de 1997", _AMZN_1997),
        _fact("Principio central de la carta de 1997", "\"It's All About the Long Term\"", "carta a los accionistas de 1997", _AMZN_1997),
    ],
    "letters": [
        {"title": "Carta a los accionistas de 1997 (Jeffrey P. Bezos)", "date": "1997", "url": _AMZN_1997},
        {"title": "Todas las cartas a los accionistas de Amazon", "date": "1997-", "url": _AMZN_LETTERS},
    ],
    "meetings": [],
    "holdings": None,
    "holdings_note": (
        "Sin datos: Bezos no presenta 13F. Su participación en Amazon figura en los registros de la SEC (enlace en fuentes) "
        "y aún no está incorporada con cifras verificadas."
    ),
    "links": [
        {"label": "Documentos de Amazon en la SEC (EDGAR)", "url": _AMZN_EDGAR},
    ],
}

PUBLIC_PROFILES["munger"] = {
    "vehicle": {
        "name": "Berkshire Hathaway (Charlie Munger, vicepresidente)",
        "type": "Vicepresidente de Berkshire Hathaway hasta su fallecimiento el 28 nov 2023 (según Berkshire)",
        "regulator_id": "Fallecido 2023-11-28",
        "manager_company": "Berkshire Hathaway Inc.",
        "start_date": "",
        "source_url": _BRK_NEWS,
    },
    "facts": [
        _fact("Fallecimiento", "28 nov 2023, 33 días antes de cumplir 100 años", "2023-11-28", _BRK_2023),
        _fact("Rol en Berkshire", "Socio de Warren Buffett en la dirección de Berkshire; Buffett le dedica la carta anual 2023", "carta anual 2023", _BRK_2023),
    ],
    "letters": [
        {"title": "Carta anual 2023 de Berkshire: «Charlie Munger - The Architect of Berkshire Hathaway»", "date": "2023", "url": _BRK_2023},
        {"title": "Comunicado de Berkshire sobre su fallecimiento (28 nov 2023)", "date": "2023", "url": _BRK_NEWS},
        {"title": "Todas las cartas de Berkshire Hathaway", "date": "1977-", "url": _BRK_LETTERS},
    ],
    "meetings": [],
    "holdings": None,
    "holdings_note": (
        "Sin datos: Munger no presentaba 13F a título personal. La cartera de Berkshire está en la ficha de Warren Buffett."
    ),
    "links": [
        {"label": "Cartas de Berkshire Hathaway", "url": _BRK_LETTERS},
    ],
}

PUBLIC_PROFILES["nick-sleep"] = {
    "vehicle": {
        "name": "Nomad Investment Partnership (Nick Sleep y Qais Zakaria)",
        "type": "Sociedad de inversión; cartas semestrales a socios de finales de 2001 a inicios de 2014",
        "regulator_id": "Cartas 2001-2014",
        "manager_company": "Nomad Investment Partnership",
        "start_date": "2001",
        "source_url": _NOMAD,
    },
    "facts": [
        _fact("Cartas publicadas", "Semestrales, de finales de 2001 a inicios de 2014", "recopilación alojada en IGY Foundation", _NOMAD),
        _fact("Evolución descrita por los autores", "Del estilo cigar butt a participaciones casi permanentes (\"from cigar butt investing to near permanent holdings\")", "recopilación alojada en IGY Foundation", _NOMAD),
    ],
    "letters": [
        {"title": "Colección completa de cartas de Nomad a los socios (2001-2014), copia aprobada alojada en IGY Foundation", "date": "2001-2014", "url": _NOMAD},
    ],
    "meetings": [],
    "holdings": None,
    "holdings_note": (
        "Sin datos: Nomad no presenta 13F público. Las posiciones se describen dentro de las cartas (enlace arriba), "
        "no como una cartera con fechas y cifras."
    ),
    "links": [
        {"label": "Cartas de Nomad (IGY Foundation, tercero)", "url": _NOMAD},
    ],
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
