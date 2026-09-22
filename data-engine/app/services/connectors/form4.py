"""Conector Form 4 (insider trading) sobre SEC EDGAR. Gratis, sin API key.

Referencias MIT consultadas (solo lectura, implementacion propia):
- efebiskin/sec-form4-parser: parse tolerante del XML <ownershipDocument>
  (dataclasses tipadas, codigos P/S, agregados purchases/sales) + fetcher
  EDGAR con rate-limit 10 req/s y User-Agent obligatorio.
- MunehisaWada/edgar-form345: Forms 3/4/5 a CSV + agregacion por
  transaction code y master.idx trimestral.

Diseno propio para CavaAI (cero dependencias nuevas, solo stdlib + httpx):
- submissions JSON de data.sec.gov para listar filings Form 4 por CIK.
- parse del XML del documento primario con xml.etree (tolerante a
  campos ausentes, como los filings reales).
- rate-limit SEC: maximo 10 req/s (intervalo minimo 0.1s) + User-Agent
  de contacto desde settings.sec_user_agent.

No se anade ninguna dependencia: NO tocar requirements.txt por esto.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

import httpx

from app.core.config import get_settings

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

# SEC fair-use: maximo 10 peticiones/segundo.
MIN_INTERVAL_SECONDS = 0.1

_lock = threading.Lock()
_last_request_at = 0.0


def resolve_user_agent() -> str:
    """User-Agent con contacto: settings.sec_user_agent (la SEC lo exige)."""
    candidate = (get_settings().sec_user_agent or "").strip()
    if "@" not in candidate:
        return "CavaAI/0.1 contact@example.com"
    return candidate


def default_headers() -> dict[str, str]:
    return {
        "User-Agent": resolve_user_agent(),
        "Accept": "application/json, text/xml, */*",
        "Accept-Encoding": "gzip, deflate",
    }


def _throttle() -> None:
    """Respeta el rate-limit SEC (10 req/s) en cliente sincrono."""
    global _last_request_at
    with _lock:
        elapsed = time.monotonic() - _last_request_at
        wait = MIN_INTERVAL_SECONDS - elapsed
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _pad_cik(cik: str | int) -> str:
    return str(cik).strip().zfill(10)


def filing_index_url(cik: str | int, accession_number: str) -> str:
    cik_number = str(int(str(cik).strip()))
    accession = str(accession_number).replace("-", "")
    return f"{ARCHIVES_URL}/{cik_number}/{accession}/"


def recent_form4_filings(
    cik: str | int,
    *,
    limit: int = 20,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Filings Form 4 recientes desde el submissions JSON (sincrono)."""
    url = SUBMISSIONS_URL.format(cik=_pad_cik(cik))
    _throttle()
    if client is not None:
        response = client.get(url, headers=default_headers())
    else:
        with httpx.Client(timeout=30, headers=default_headers()) as owned:
            response = owned.get(url)
    response.raise_for_status()
    payload = response.json()
    recent = (payload.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber", []) or []
    cik_number = str(int(str(cik).strip()))
    items: list[dict] = []

    def _col(name: str, index: int):
        values = recent.get(name, []) or []
        return values[index] if index < len(values) else None

    for index, accession in enumerate(accessions):
        form = str(_col("form", index) or "").strip().upper()
        # Form 4 y sus enmiendas (4/A). Las enmiendas corrigen un filing
        # previo; excluirlas dejaba correcciones invisibles.
        if form not in {"4", "4/A"}:
            continue
        primary = _col("primaryDocument", index)
        accession_nodash = str(accession).replace("-", "")
        index_url = f"{ARCHIVES_URL}/{cik_number}/{accession_nodash}/"
        items.append(
            {
                "form": form,
                "accession_number": accession,
                "filing_date": _col("filingDate", index),
                "report_date": _col("reportDate", index),
                "primary_document": primary,
                "index_url": index_url,
                "document_url": f"{index_url}{primary}" if primary else index_url,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_filing_xml(
    document_url: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    """Descarga el XML del documento primario (solo hosts sec.gov)."""
    from urllib.parse import urlparse

    hostname = (urlparse(document_url).hostname or "").lower()
    if hostname not in {"sec.gov", "www.sec.gov"}:
        raise ValueError("Form 4 document URL must use sec.gov")
    _throttle()
    if client is not None:
        response = client.get(document_url, headers=default_headers())
    else:
        with httpx.Client(timeout=30, headers=default_headers()) as owned:
            response = owned.get(document_url)
    response.raise_for_status()
    return response.text


# ---------------- Parse del XML <ownershipDocument> ----------------


def _text(elem: ET.Element | None, path: str) -> str | None:
    if elem is None:
        return None
    node = elem.find(path)
    if node is None:
        return None
    if node.text and node.text.strip():
        return node.text.strip()
    value = node.find("value")
    if value is not None and value.text and value.text.strip():
        return value.text.strip()
    return None


def _decimal(elem: ET.Element | None, path: str) -> Decimal | None:
    raw = _text(elem, path)
    if raw is None:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def _date(elem: ET.Element | None, path: str) -> date | None:
    raw = _text(elem, path)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _flag(elem: ET.Element | None, path: str) -> bool:
    raw = _text(elem, path)
    return raw is not None and raw.strip() in {"1", "true", "True"}


def parse_form4_xml(source: str | bytes) -> dict:
    """Parsea un Form 4 XML a dict con ticker, insider, rol, P/S, acciones, precio, valor.

    Tolerante a campos ausentes (los filings reales omiten hojas opcionales).
    Lanza ValueError si el XML no es un <ownershipDocument>.
    """
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ValueError(f"malformed Form 4 XML: {exc}") from exc
    if root.tag != "ownershipDocument":
        raise ValueError(f"expected root <ownershipDocument>, got <{root.tag}>")

    issuer = root.find("issuer")
    ticker = _text(issuer, "issuerTradingSymbol")
    issuer_name = _text(issuer, "issuerName") or ""
    issuer_cik = _text(issuer, "issuerCik") or ""
    period = _date(root, "periodOfReport")

    reporters: list[dict] = []
    for node in root.findall("reportingOwner"):
        rid = node.find("reportingOwnerId")
        rel = node.find("reportingOwnerRelationship")
        reporters.append(
            {
                "cik": _text(rid, "rptOwnerCik") or "",
                "name": _text(rid, "rptOwnerName") or "",
                "is_director": _flag(rel, "isDirector"),
                "is_officer": _flag(rel, "isOfficer"),
                "is_ten_percent_owner": _flag(rel, "isTenPercentOwner"),
                "officer_title": _text(rel, "officerTitle"),
            }
        )

    def _role(rep: dict) -> str:
        parts = []
        if rep["is_director"]:
            parts.append("director")
        if rep["is_officer"]:
            title = rep.get("officer_title")
            parts.append(f"officer ({title})" if title else "officer")
        if rep["is_ten_percent_owner"]:
            parts.append("10% owner")
        return ", ".join(parts) or "insider"

    transactions: list[dict] = []
    tables = [
        (False, root.findall("nonDerivativeTable/nonDerivativeTransaction")),
        (True, root.findall("derivativeTable/derivativeTransaction")),
    ]
    # Caso general: un Form 4 trae un solo reporter y todas las filas son suyas.
    # Multi-reporter (filing conjunto): el XML NO ata filas a reporters, asi
    # que nunca se atribuye en silencio al primero — se marca la transaccion
    # como filing conjunto y se listan todos los reporters.
    main_rep = (reporters or [{}])[0]
    multi_reporter = len(reporters) > 1
    if multi_reporter:
        joint_names = " / ".join(rep.get("name", "") for rep in reporters if rep.get("name"))
    for is_derivative, nodes in tables:
        for node in nodes:
            coding = node.find("transactionCoding")
            amounts = node.find("transactionAmounts")
            code = (_text(coding, "transactionCode") or "").strip().upper() or None
            acquired = (_text(amounts, "transactionAcquiredDisposedCode") or "").strip().upper() or None
            shares = _decimal(amounts, "transactionShares")
            price = _decimal(amounts, "transactionPricePerShare")
            value = None
            if shares is not None and price is not None:
                value = shares * price
            tx_date = _date(node, "transactionDate")
            transactions.append(
                {
                    "ticker": ticker,
                    "issuer_name": issuer_name,
                    "issuer_cik": issuer_cik,
                    "period_of_report": period.isoformat() if period else None,
                    "insider": joint_names if multi_reporter else main_rep.get("name", ""),
                    "insider_cik": "" if multi_reporter else main_rep.get("cik", ""),
                    "multi_reporter": multi_reporter,
                    "reporters_count": len(reporters),
                    "attribution": "joint_filing" if multi_reporter else "single_reporter",
                    "role": ("multiple insiders" if multi_reporter else (_role(main_rep) if reporters else "insider")),
                    "officer_title": main_rep.get("officer_title"),
                    "is_officer": bool(main_rep.get("is_officer")),
                    "type": code,  # codigo SEC crudo: P = compra (mercado abierto O privada), S = venta
                    "acquired_disposed": acquired,  # A / D
                    "shares": float(shares) if shares is not None else None,
                    "price": float(price) if price is not None else None,
                    "value": float(value) if value is not None else None,
                    "date": tx_date.isoformat() if tx_date else None,
                    "is_derivative": is_derivative,
                }
            )

    return {
        "ticker": ticker,
        "issuer_name": issuer_name,
        "issuer_cik": issuer_cik,
        "period_of_report": period.isoformat() if period else None,
        "reporters": reporters,
        "transactions": transactions,
    }


def is_open_market_buy(tx: dict) -> bool:
    """Compra insider por codigo P + adquirida (A).

    OJO: el codigo P de la SEC cubre compras en mercado abierto Y compras
    privadas; el XML no siempre lo distingue. El nombre de la funcion se
    mantiene por compatibilidad, pero las cadenas visibles al usuario deben
    decir "compra (codigo P: mercado abierto o privado)".
    """
    return tx.get("type") == "P" and tx.get("acquired_disposed") == "A"
