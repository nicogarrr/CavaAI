"""Backfill de EPS/acciones diluidas para filers por clases (Visa, BRK.B...).

La API companyfacts de la SEC excluye hechos con dimensiones, asi que estos
emisores se quedan sin eps_diluted/shares_diluted en la ingesta estandar.
Este servicio lee la instancia XBRL del ultimo 10-K y recupera los hechos de
la clase que corresponde al ticker cotizado, con la misma forma de escritura
que la ingesta SEC (period '<end>:FY', fiscal_quarter='FY', source_type='SEC',
is_reported=True) para que screener y demas consumidores los vean igual.

Reglas honestas: solo se escribe lo que el emisor declaro para la clase
preferida (config por ticker, revisada a mano); si la clase preferida no esta
y hay UNA sola clase declarada, se usa esa; si hay varias y ninguna es la
preferida, no se escribe nada. Nunca se sobrescribe un hecho existente.
"""

from __future__ import annotations

import gzip
import io
import json
import urllib.request
from decimal import Decimal
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, Document, FinancialFact
from app.services.connectors.sec_edgar import default_headers
from app.services.connectors.sec_xbrl_instance import (
    METRIC_TAGS,
    DimensionedFact,
    parse_instance_dimensioned_facts,
)

# Clase cuyos hechos representan al ticker cotizado. Nombre LOCAL del miembro
# (sin prefijo de namespace: cada emisor usa el suyo). Revisada a mano.
CLASS_MEMBER_PREFERENCE: dict[str, str] = {
    "V": "CommonClassAMember",
    "BRK.B": "EquivalentClassBMember",
}

_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/"


@dataclass(frozen=True)
class ClassEpsResult:
    ticker: str
    facts_written: int
    member_used: str | None
    periods: tuple[str, ...]
    skipped_reason: str | None = None


def pick_member(facts: list[DimensionedFact], preferred: str | None) -> str | None:
    """Miembro dimensional a usar: el preferido si esta; si hay uno solo, ese.

    Con varios miembros y sin preferido presente devuelve None (no se elige
    a ciegas: escribir la clase equivocada seria fabricar el ratio).
    """
    members = {m for f in facts for m in f.members}
    if preferred and preferred in members:
        return preferred
    if len(members) == 1:
        return next(iter(members))
    return None


def _read_response(response) -> bytes:
    data = response.read()
    # EDGAR sirve gzip cuando el cliente lo anuncia; urllib no descomprime.
    if response.headers.get("Content-Encoding") == "gzip":
        data = gzip.decompress(data)
    return data


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=default_headers())
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(_read_response(response).decode("utf-8"))


def _fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers=default_headers())
    with urllib.request.urlopen(request, timeout=60) as response:
        return _read_response(response)


def _latest_10k_instance_url(cik: str, fetch_json: Callable[[str], dict]) -> str | None:
    submissions = fetch_json(_SUBMISSIONS_URL.format(cik=cik.zfill(10)))
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    for index, form in enumerate(forms):
        if form != "10-K":
            continue
        accession = recent["accessionNumber"][index]
        acc_nodash = accession.replace("-", "")
        index_doc = fetch_json(
            f"{_ARCHIVES_URL.format(cik_int=int(cik), acc_nodash=acc_nodash)}index.json"
        )
        for item in index_doc.get("directory", {}).get("item", []):
            name = item.get("name", "")
            if name.endswith("_htm.xml"):
                return f"{_ARCHIVES_URL.format(cik_int=int(cik), acc_nodash=acc_nodash)}{name}"
        return None
    return None


def _get_or_create_document(db: Session, company: Company, url: str) -> Document:
    title = f"SEC XBRL instance (class facts) - {company.ticker}"
    document = db.scalar(
        select(Document).where(
            Document.company_id == company.id,
            Document.source_type == "SEC",
            Document.title == title,
        )
    )
    if document:
        return document
    document = Document(
        company_id=company.id,
        title=title,
        source_type="SEC",
        source_url=url,
        metadata_={"provider": "SEC", "xbrl_instance": True},
    )
    db.add(document)
    db.flush()
    return document


def backfill_class_based_eps(
    db: Session,
    company: Company,
    *,
    cik: str,
    fetch_json: Callable[[str], dict] = _fetch_json,
    fetch_bytes: Callable[[str], bytes] = _fetch_bytes,
) -> ClassEpsResult:
    """Escribe eps_diluted/shares_diluted del 10-K para un filer por clases.

    Idempotente: un hecho ya existente (misma metrica y periodo) no se toca.
    """
    url = _latest_10k_instance_url(cik, fetch_json)
    if url is None:
        return ClassEpsResult(company.ticker, 0, None, (), skipped_reason="sin instancia 10-K")
    facts = parse_instance_dimensioned_facts(io.BytesIO(fetch_bytes(url)))
    if not facts:
        return ClassEpsResult(company.ticker, 0, None, (), skipped_reason="sin hechos dimensionados")
    member = pick_member(facts, CLASS_MEMBER_PREFERENCE.get(company.ticker.upper()))
    if member is None:
        return ClassEpsResult(
            company.ticker, 0, None, (), skipped_reason="varias clases sin preferida"
        )
    document = _get_or_create_document(db, company, url)
    written = 0
    periods: list[str] = []
    used_tags: set[str] = set()
    # La instancia repite el mismo hecho en varias secciones (balance, notas,
    # cover) con contextos distintos: dedup en memoria por (metrica, periodo),
    # la comprobacion en BD no basta con sesiones sin autoflush.
    seen_periods: set[tuple[str, str]] = set()
    for metric, tags in METRIC_TAGS.items():
        metric_facts = [f for f in facts if f.tag in tags and member in f.members and f.end]
        # Solo el tag prioritario con hechos: diluido si existe, basic si no.
        for tag in tags:
            tag_facts = [f for f in metric_facts if f.tag == tag]
            if not tag_facts:
                continue
            for fact in tag_facts:
                period = f"{fact.end.isoformat()}:FY"
                if (metric, period) in seen_periods:
                    continue
                seen_periods.add((metric, period))
                exists = db.scalar(
                    select(FinancialFact.id).where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.metric == metric,
                        FinancialFact.period == period,
                    )
                )
                if exists:
                    continue
                db.add(
                    FinancialFact(
                        company_id=company.id,
                        metric=metric,
                        value=fact.value,
                        unit="USD/share" if metric == "eps_diluted" else "shares",
                        period=period,
                        fiscal_year=fact.end.year,
                        fiscal_quarter="FY",
                        source_id=document.id,
                        source_type="SEC",
                        is_reported=True,
                        confidence=Decimal("0.95"),
                    )
                )
                written += 1
                used_tags.add(tag)
                if period not in periods:
                    periods.append(period)
            break
    if used_tags and document.metadata_ is not None:
        document.metadata_ = {
            **(document.metadata_ or {}),
            "class_member": member,
            "xbrl_tags": sorted(used_tags),
        }
    db.flush()
    return ClassEpsResult(company.ticker, written, member, tuple(periods))

