"""Chunks buscables (RAG) generados desde financial_facts reales.

Los Document de fundamentales (SEC/ESEF) se crean sin contenido parseado, asi
que rebuild_tenant no indexaba ningun dato financiero: el RAG solo tenia la
biblioteca de conocimiento. Este servicio genera un chunk por empresa,
ejercicio y fuente con las cifras persistidas en financial_facts (ningun
numero se escribe a mano; el texto declara su fuente), los cuelga del Document
fuente y los regenera en cada refresh de fundamentales. RAGIndex los indexa
despues (ingest_document / rebuild_tenant).
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Company, Document, DocumentChunk, FinancialFact

FACT_SOURCES = ("SEC", "ESEF")

METRIC_LABELS: dict[str, str] = {
    "revenue": "ingresos",
    "revenue_growth": "crecimiento de ingresos",
    "gross_margin": "margen bruto",
    "operating_income": "resultado operativo",
    "operating_margin": "margen operativo",
    "ebitda": "EBITDA",
    "net_income": "beneficio neto",
    "net_margin": "margen neto",
    "eps_diluted": "BPA diluido",
    "income_before_tax": "resultado antes de impuestos",
    "income_tax_expense": "impuesto sobre beneficios",
    "effective_tax_rate": "tipo impositivo efectivo",
    "interest_expense": "gastos financieros",
    "operating_cash_flow": "flujo de caja operativo",
    "capital_expenditure": "capex",
    "free_cash_flow": "flujo de caja libre",
    "depreciation_amortization": "depreciacion y amortizacion",
    "dividends_paid": "dividendos pagados",
    "common_stock_repurchased": "recompra de acciones",
    "cash_and_equivalents": "caja y equivalentes",
    "total_assets": "activos totales",
    "total_liabilities": "pasivos totales",
    "total_equity": "patrimonio neto",
    "debt_to_equity": "deuda sobre patrimonio",
}

_RATIO_UNITS = {"decimal", "ratio", "percent"}


def _es_number(value: float) -> str:
    """1.234,56 en notacion es-ES."""
    return f"{value:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def _format_value(value: Decimal, unit: str) -> str:
    number = float(value)
    unit_clean = unit.replace("iso4217:", "")
    if unit_clean in _RATIO_UNITS:
        return f"{_es_number(number * 100)} %"
    if unit_clean.endswith("/share") or unit_clean.endswith("/xbrli:shares"):
        return f"{_es_number(number)} {unit_clean.split('/')[0]}/accion"
    absolute = abs(number)
    if absolute >= 1e9:
        return f"{_es_number(number / 1e9)} mil M {unit_clean}"
    if absolute >= 1e6:
        return f"{_es_number(number / 1e6)} M {unit_clean}"
    return f"{_es_number(number)} {unit_clean}"


def _render_chunk(
    company: Company,
    source: str,
    fiscal_year: int,
    facts: list[FinancialFact],
) -> str:
    ordered = sorted(
        facts,
        key=lambda f: (list(METRIC_LABELS).index(f.metric) if f.metric in METRIC_LABELS else len(METRIC_LABELS), f.metric),
    )
    parts = [
        f"{METRIC_LABELS.get(fact.metric, fact.metric)} {_format_value(fact.value, fact.unit)}"
        for fact in ordered
        if fact.value is not None
    ]
    return (
        f"{company.name} ({company.ticker}) - ejercicio fiscal {fiscal_year} "
        f"(fuente {source}, hechos reportados): " + "; ".join(parts) + "."
    )


def sync_company_fact_chunks(db: Session, company: Company) -> dict[str, int]:
    """Regenera los chunks RAG del Document SEC/ESEF de la empresa desde sus
    financial_facts actuales. Idempotente: borra y reescribe. Si no quedan
    hechos de una fuente, sus chunks desaparecen (estado honesto)."""
    stats = {"sources": 0, "chunks": 0}
    for source in FACT_SOURCES:
        document = db.scalar(
            select(Document)
            .where(Document.company_id == company.id, Document.source_type == source)
            .order_by(Document.id)
            .limit(1)
        )
        if document is None:
            continue
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        facts = list(
            db.scalars(
                select(FinancialFact).where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.source_type == source,
                )
            ).all()
        )
        by_year: dict[int, list[FinancialFact]] = {}
        for fact in facts:
            if fact.fiscal_year is not None and fact.value is not None:
                by_year.setdefault(fact.fiscal_year, []).append(fact)
        for index, (year, year_facts) in enumerate(sorted(by_year.items(), reverse=True)):
            text = _render_chunk(company, source, year, year_facts)
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    text=text,
                    token_count=len(text.split()),
                )
            )
            stats["chunks"] += 1
        stats["sources"] += 1
    db.flush()
    return stats
