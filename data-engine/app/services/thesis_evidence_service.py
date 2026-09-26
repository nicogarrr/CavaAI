"""Best-effort evidence bundle assembled at thesis-generate time.

Ley: ninguna tesis sale ``insufficient_data`` si la empresa tiene filings
o precio de mercado que podamos traer. Este servicio intenta, en este
orden y cada fuente con su propio try/except:

  1. Fundamentales SEC EDGAR (companyfacts, sin API key): revenue, shares,
     assets, etc. -> FinancialFacts + Document SEC.
  2. Precio Finnhub (quote) -> MarketPrice; perfil (profile2) -> nombre
     real + market cap.
  3. Filings recientes 10-K/10-Q/8-K (EDGAR submissions) -> Documents SEC.
  4. Noticias materiales ya ingeridas (pipeline news: NewsEvent).
  5. Proximo earnings (calendario NASDAQ existente) + transcripcion
     existente (si no hay, hueco 'pendiente transcripcion').
  6. Investor-relations (IRConnector sobre company.ir_url) -> Documents IR.
  7. Tesis externas: NO se scrapean paywalls; se listan Documents con
     source_type='external_thesis' (via POST /documents/ingest-url o RSS)
     y si no hay, hueco accionable.

Nunca lanza: cada fuente degrada a ``status="pending"`` con el motivo y
un hueco accionable. Nada inventado: solo se persiste lo que devuelve
el proveedor; la ausencia queda marcada como pendiente.

Hermeticidad en tests: la red real pasa por `_await_sync`, que bajo
pytest (``PYTEST_CURRENT_TEST``) falla rapido sin salir a red. Los tests
inyectan datos sustituyendo los metodos `_fetch_*` con mocks, que no
pasan por `_await_sync` y por tanto siguen funcionando. Asi la suite
existente no se vuelve lenta ni flaky por EDGAR/NASDAQ/IR reales.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, Document, FinancialFact, MarketPrice, NewsEvent, Transcript
from app.services.connectors import earnings_calendar as earnings_calendar_connector
from app.services.connectors import sec_edgar as sec_edgar_connector
from app.services.connectors.finnhub import FinnhubClient
from app.services.connectors.ir import IRConnector

# Metrica -> (tags us-gaap por preferencia, unidad). El primer tag que
# informa gana; nunca se suman tags.
SEC_EVIDENCE_TAGS: dict[str, tuple[list[str], str]] = {
    "revenue": (
        ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
        "USD",
    ),
    "shares_diluted": (
        ["WeightedAverageNumberOfDilutedSharesOutstanding", "CommonStockSharesOutstanding"],
        "shares",
    ),
    "total_assets": (["Assets"], "USD"),
    "net_income": (["NetIncomeLoss", "ProfitLoss"], "USD"),
    "operating_cash_flow": (["NetCashProvidedByUsedInOperatingActivities"], "USD"),
    "cash_and_equivalents": (
        ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
        "USD",
    ),
    "total_debt": (
        ["LongTermDebtNoncurrent", "LongTermDebt", "DebtLongtermAndShorttermCombinedAmount"],
        "USD",
    ),
}

ANNUAL_FORMS = {"10-K", "20-F"}
FILING_FORMS = ("10-K", "10-Q", "8-K")
MAX_FILING_DOCUMENTS = 8
MAX_IR_DOCUMENTS = 10
MAX_NEWS_ITEMS = 5
EARNINGS_LOOKAHEAD_DAYS = 14
FETCH_TIMEOUT_S = 20.0

EXTERNAL_THESIS_HOWTO = (
    "Pega URLs via POST /api/sources/documents/ingest-url "
    "(source_type='external_thesis') o suscribe el RSS del autor; "
    "no se scrapean paywalls."
)


def _await_sync(factory, timeout: float = FETCH_TIMEOUT_S):
    """Ejecuta una corrutina desde codigo sincrono con timeout.

    ``factory`` es un callable sin args que crea la corrutina (asi puede
    crearse en el hilo que la ejecuta). Funciona tanto sin event loop
    (caso normal del endpoint sync) como dentro de uno (hilo dedicado).

    Hermeticidad: bajo pytest la red real esta vetada (los tests usan
    mocks de `_fetch_*`, que no pasan por aqui).
    """
    if os.getenv("PYTEST_CURRENT_TEST"):
        raise RuntimeError("hermetic tests: live network disabled (mock _fetch_*)")

    async def _bounded():
        return await asyncio.wait_for(factory(), timeout)

    from app.services.async_bridge import run_from_any_context

    return run_from_any_context(_bounded())


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _pending(source: str, detail: str, action: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "pending", "source": source, "detail": detail}
    if action:
        payload["action"] = action
    return payload


class ThesisEvidenceService:
    """Reune y persiste el paquete de evidencia best-effort para una tesis."""

    # -- seansa de red (mockeables en tests) --------------------------------
    def _fetch_cik(self, ticker: str) -> str | None:
        return _await_sync(lambda: sec_edgar_connector.cik_for_ticker(ticker))

    def _fetch_company_facts(self, cik: str) -> dict[str, Any]:
        return _await_sync(lambda: sec_edgar_connector.company_facts(cik))

    def _fetch_filings(self, cik: str) -> list[dict[str, Any]]:
        return _await_sync(
            lambda: sec_edgar_connector.recent_filings(cik, forms=FILING_FORMS, limit=MAX_FILING_DOCUMENTS)
        )

    def _fetch_quote(self, ticker: str) -> dict[str, Any]:
        return _await_sync(lambda: FinnhubClient().quote(ticker))

    def _fetch_profile(self, ticker: str) -> dict[str, Any]:
        return _await_sync(lambda: FinnhubClient().profile(ticker))

    def _fetch_earnings(self) -> dict[str, Any]:
        today = date.today()
        return _await_sync(
            lambda: earnings_calendar_connector.fetch_earnings_range(
                today, today + timedelta(days=EARNINGS_LOOKAHEAD_DAYS)
            ),
            timeout=30.0,
        )

    def _fetch_ir(self, ir_url: str, ticker: str):
        return _await_sync(
            lambda: IRConnector().poll(ir_url, ticker=ticker, max_pages=2, max_items=MAX_IR_DOCUMENTS)
        )

    # -- entrada principal ---------------------------------------------------
    def collect(self, db: Session, company: Company) -> dict[str, Any]:
        """Reune evidencia, persiste lo conseguido y devuelve el bundle.

        Nunca lanza: si todo falla, cada bloque queda en pending y la tesis
        sale con el esqueleto honesto actual.
        """
        ticker = company.ticker.upper()
        bundle: dict[str, Any] = {"ticker": ticker, "sources": {}}
        cik: str | None = getattr(company, "cik", None) or None

        if not cik:
            try:
                cik = self._fetch_cik(ticker)
            except Exception as exc:  # noqa: BLE001 - best-effort
                cik = None
                bundle["sources"]["cik"] = _pending(
                    "SEC EDGAR ticker map", f"CIK no resuelto: {exc}"[:200]
                )
        if cik:
            bundle["sources"]["cik"] = {"status": "ok", "source": "SEC EDGAR", "cik": cik}

        bundle["sources"]["fundamentals"] = self._ingest_fundamentals(db, company, cik)
        bundle["sources"]["market"] = self._ingest_market(db, company)
        bundle["sources"]["filings"] = self._ingest_filings(db, company, cik)
        bundle["sources"]["news"] = self._collect_news(db, company)
        bundle["sources"]["earnings"] = self._collect_earnings(db, company)
        bundle["sources"]["transcript"] = self._collect_transcript(db, company)
        bundle["sources"]["ir"] = self._ingest_ir(db, company)
        bundle["sources"]["external_theses"] = self._collect_external_theses(db, company)
        db.flush()
        return bundle

    # -- 1. fundamentales SEC -------------------------------------------------
    def _ingest_fundamentals(
        self, db: Session, company: Company, cik: str | None
    ) -> dict[str, Any]:
        if not cik:
            return _pending(
                "SEC EDGAR companyfacts",
                "Sin CIK no hay companyfacts (empresa no filer USA o EDGAR inaccesible).",
            )
        try:
            facts_payload = self._fetch_company_facts(cik)
        except Exception as exc:  # noqa: BLE001 - best-effort
            return _pending("SEC EDGAR companyfacts", f"EDGAR inaccesible: {exc}"[:200])
        us_gaap = ((facts_payload or {}).get("facts") or {}).get("us-gaap") or {}
        extracted = self._extract_latest_annual(us_gaap)
        if not extracted:
            return _pending(
                "SEC EDGAR companyfacts",
                f"CIK {cik} sin metricas us-gaap aprovechables.",
            )
        document = self._get_or_create_document(
            db,
            company,
            title=f"SEC XBRL companyfacts - {company.ticker}",
            source_type="SEC",
            source_url=(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json"
            ),
        )
        # Aditivo, nunca destructivo: refresh/sec es el duenio del historico
        # SEC completo; aqui solo rellenamos el ultimo anual si falta. Antes
        # este paso borraba TODOS los facts SEC y dejaba 1 ano por metrica,
        # tirando abajo el DCF (insufficient_data) tras cada tesis.
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        existing = {
            (fact.metric, fact.period)
            for fact in db.scalars(
                select(FinancialFact).where(
                    FinancialFact.company_id == company.id,
                    FinancialFact.source_type == "SEC",
                    tenant_filter,
                )
            )
        }
        imported = 0
        skipped_existing = 0
        for metric, info in extracted.items():
            if (metric, info["period"]) in existing:
                skipped_existing += 1
                continue
            value = _decimal(info["value"])
            if value is None:
                continue
            db.add(
                FinancialFact(
                    company_id=company.id,
                    metric=metric,
                    value=value,
                    unit=info["unit"],
                    period=info["period"],
                    fiscal_year=info["fiscal_year"],
                    fiscal_quarter=info.get("fiscal_quarter"),
                    source_id=document.id,
                    source_type="SEC",
                    is_reported=True,
                    confidence=Decimal("0.95"),
                )
            )
            imported += 1
        db.flush()
        if imported == 0 and skipped_existing == 0:
            return _pending("SEC EDGAR companyfacts", "Hechos sin valor numerico aprovechable.")
        return {
            "status": "ok",
            "source": "SEC EDGAR companyfacts",
            "facts_imported": imported,
            "already_present": skipped_existing,
            "metrics": sorted(extracted.keys()),
            "document_id": document.id,
        }

    def _extract_latest_annual(self, us_gaap: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Ultimo 10-K/20-F por metrica (fallback: ultimo 10-Q)."""
        out: dict[str, dict[str, Any]] = {}
        for metric, (tags, unit) in SEC_EVIDENCE_TAGS.items():
            for tag in tags:
                entries = ((us_gaap.get(tag) or {}).get("units") or {}).get(unit, [])
                annual = [
                    e
                    for e in entries
                    if isinstance(e, dict)
                    and str(e.get("form", "")).upper() in ANNUAL_FORMS
                    and e.get("val") is not None
                    and e.get("end")
                ]
                pool = annual or [
                    e
                    for e in entries
                    if isinstance(e, dict) and e.get("val") is not None and e.get("end")
                ]
                if not pool:
                    continue
                pool.sort(key=lambda e: (str(e.get("filed", "")), str(e.get("end", ""))))
                latest = pool[-1]
                end = str(latest["end"])
                try:
                    fiscal_year = int(end[:4])
                except ValueError:
                    fiscal_year = None
                is_annual = str(latest.get("form", "")).upper() in ANNUAL_FORMS
                out[metric] = {
                    "value": latest["val"],
                    "unit": unit,
                    "period": f"{end}:FY" if is_annual else f"{end}:{latest.get('form')}",
                    "fiscal_year": fiscal_year,
                    "fiscal_quarter": "FY" if is_annual else None,
                    "concept": tag,
                    "form": latest.get("form"),
                }
                break
        return out

    # -- 2. precio + perfil Finnhub -------------------------------------------
    def _ingest_market(self, db: Session, company: Company) -> dict[str, Any]:
        ticker = company.ticker.upper()
        result: dict[str, Any] = {"status": "pending", "source": "Finnhub"}
        try:
            quote = self._fetch_quote(ticker)
        except Exception as exc:  # noqa: BLE001 - best-effort
            result["detail"] = f"Quote inaccesible: {exc}"[:200]
            quote = None
        price = _decimal((quote or {}).get("c")) if quote else None
        if price is not None and price > 0:
            today = datetime.now(UTC).date()
            existing = db.scalar(
                select(MarketPrice).where(
                    MarketPrice.company_id == company.id, MarketPrice.date == today
                )
            )
            if existing:
                existing.close = price
                existing.adj_close = price
                existing.source = "Finnhub"
            else:
                db.add(
                    MarketPrice(
                        company_id=company.id,
                        date=today,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        adj_close=price,
                        source="Finnhub",
                    )
                )
            result.update({"status": "ok", "price": float(price)})
        else:
            result["detail"] = result.get("detail") or "Quote sin precio util (c<=0 o vacio)."
        try:
            profile = self._fetch_profile(ticker)
        except Exception as exc:  # noqa: BLE001 - best-effort
            result["profile_detail"] = f"Perfil inaccesible: {exc}"[:200]
            profile = None
        if profile:
            name = str(profile.get("name") or "").strip()
            if name and (not (company.name or "").strip() or company.name.strip().upper() == ticker):
                company.name = name
                db.add(company)
                result["name"] = name
            market_cap = _decimal(profile.get("marketCapitalization"))
            if market_cap is not None and market_cap > 0:
                # marketCapitalization de Finnhub viene en millones de USD.
                value = market_cap * Decimal("1000000")
                period = datetime.now(UTC).date().isoformat()
                already = db.scalar(
                    select(FinancialFact).where(
                        FinancialFact.company_id == company.id,
                        FinancialFact.metric == "market_cap",
                        FinancialFact.period == period,
                        FinancialFact.source_type == "Finnhub",
                    )
                )
                if already is None:
                    db.add(
                        FinancialFact(
                            company_id=company.id,
                            metric="market_cap",
                            value=value,
                            unit="USD",
                            period=period,
                            source_id=None,
                            source_type="Finnhub",
                            is_reported=True,
                            confidence=Decimal("0.75"),
                        )
                    )
                result["market_cap"] = float(value)
            exchange = str(profile.get("exchange") or "").strip()
            if exchange and not (company.exchange or "").strip():
                company.exchange = exchange
                db.add(company)
        db.flush()
        if result["status"] != "ok" and "market_cap" not in result and "name" not in result:
            result.setdefault("detail", "Sin precio ni perfil (sin FINNHUB_API_KEY o red).")
        return result

    # -- 3. filings como documentos -------------------------------------------
    def _ingest_filings(
        self, db: Session, company: Company, cik: str | None
    ) -> dict[str, Any]:
        if not cik:
            return _pending("SEC EDGAR submissions", "Sin CIK no hay filings.")
        try:
            filings = self._fetch_filings(cik) or []
        except Exception as exc:  # noqa: BLE001 - best-effort
            return _pending("SEC EDGAR submissions", f"Submissions inaccesible: {exc}"[:200])
        created = 0
        items: list[dict[str, Any]] = []
        for filing in filings[:MAX_FILING_DOCUMENTS]:
            form = filing.get("form")
            url = filing.get("document_url") or filing.get("index_url")
            filed = filing.get("filing_date")
            items.append({"form": form, "filing_date": filed, "url": url})
            if not url:
                continue
            exists = db.scalar(select(Document.id).where(Document.source_url == url).limit(1))
            if exists:
                continue
            db.add(
                Document(
                    company_id=company.id,
                    title=f"{company.ticker} {form} filed {filed}",
                    source_type="SEC",
                    source_url=url,
                    metadata_={
                        "form": form,
                        "filing_date": filed,
                        "accession_number": filing.get("accession_number"),
                        "provider": "SEC EDGAR submissions",
                    },
                )
            )
            created += 1
        db.flush()
        if not items:
            return _pending("SEC EDGAR submissions", "Sin 10-K/10-Q/8-K recientes.")
        return {
            "status": "ok",
            "source": "SEC EDGAR submissions",
            "items": items,
            "documents_created": created,
        }

    # -- 4. noticias (solo lectura del pipeline news) --------------------------
    def _collect_news(self, db: Session, company: Company) -> dict[str, Any]:
        rows = list(
            db.scalars(
                select(NewsEvent)
                .where(NewsEvent.company_id == company.id)
                .order_by(desc(NewsEvent.materiality_score), desc(NewsEvent.date))
                .limit(MAX_NEWS_ITEMS)
            ).all()
        )
        if not rows:
            return _pending(
                "news pipeline (NewsEvent)",
                "Sin noticias ingeridas para este ticker.",
                action="Ingiere via POST /api/news/ingest o espera al worker de news.",
            )
        return {
            "status": "ok",
            "source": "news pipeline (NewsEvent)",
            "items": [
                {
                    "title": r.title,
                    "date": r.date.isoformat() if r.date else None,
                    "source": r.source,
                    "materiality": r.materiality_score,
                    "url": r.url,
                }
                for r in rows
            ],
        }

    # -- 5a. proximo earnings ---------------------------------------------------
    def _collect_earnings(self, db: Session, company: Company) -> dict[str, Any]:
        del db  # solo red + traza; no escribe en este bloque
        try:
            payload = self._fetch_earnings() or {}
        except Exception as exc:  # noqa: BLE001 - best-effort
            return _pending(
                "NASDAQ earnings calendar",
                f"Calendario inaccesible: {exc}"[:200],
                action="Revisa GET /api/calendar/earnings cuando haya red.",
            )
        wanted = company.ticker.upper()
        coming = sorted(
            (
                e
                for e in (payload.get("events") or [])
                if str(e.get("symbol", "")).upper() == wanted and e.get("date")
            ),
            key=lambda e: str(e.get("date")),
        )
        if not coming:
            return _pending(
                "NASDAQ earnings calendar",
                f"Sin earnings de {wanted} en los proximos {EARNINGS_LOOKAHEAD_DAYS} dias.",
                action="Revisa GET /api/calendar/earnings con un rango mayor.",
            )
        nxt = coming[0]
        return {
            "status": "ok",
            "source": "NASDAQ earnings calendar",
            "next_date": nxt.get("date"),
            "time": nxt.get("time"),
            "eps_forecast": nxt.get("eps_forecast"),
        }

    # -- 5b. transcripcion -------------------------------------------------------
    def _collect_transcript(self, db: Session, company: Company) -> dict[str, Any]:
        row = db.scalar(
            select(Transcript)
            .where(Transcript.company_id == company.id)
            .order_by(desc(Transcript.id))
            .limit(1)
        )
        if row is None:
            return _pending(
                "transcripts",
                "Pendiente transcripcion: sin fuente gratuita disponible.",
                action="Importa el texto via ManualTranscriptImportService.import_text.",
            )
        return {
            "status": "ok",
            "source": "transcripts",
            "title": row.title,
            "period": row.period,
        }

    # -- 6. IR -------------------------------------------------------------------
    def _ingest_ir(self, db: Session, company: Company) -> dict[str, Any]:
        ir_url = (getattr(company, "ir_url", None) or "").strip()
        if not ir_url:
            return _pending(
                "IR de la empresa",
                "Sin ir_url en el master; hueco marcado.",
                action="Anade ir_url al company master.",
            )
        try:
            result = self._fetch_ir(ir_url, company.ticker.upper())
        except Exception as exc:  # noqa: BLE001 - best-effort
            return _pending(
                "IR de la empresa",
                f"IR inaccesible ({ir_url}): {exc}"[:200],
                action="Reintenta o pega la presentacion via /documents/ingest-url.",
            )
        items = getattr(result, "items", None) or []
        created = 0
        listed: list[dict[str, Any]] = []
        for item in items[:MAX_IR_DOCUMENTS]:
            listed.append({"title": item.title, "url": item.url})
            if not item.url:
                continue
            exists = db.scalar(
                select(Document.id).where(Document.source_url == item.url).limit(1)
            )
            if exists:
                continue
            db.add(
                Document(
                    company_id=company.id,
                    title=item.title or f"IR release - {company.ticker}",
                    source_type="IR",
                    source_url=item.url,
                    metadata_={"provider": "company IR", "ir_url": ir_url},
                )
            )
            created += 1
        db.flush()
        errors = getattr(result, "errors", None) or []
        if not listed:
            return _pending(
                "IR de la empresa",
                f"IR sin releases detectados ({'; '.join(errors)[:200]}).",
                action="Pega la presentacion via /documents/ingest-url.",
            )
        return {
            "status": "ok",
            "source": f"company IR ({ir_url})",
            "items": listed,
            "documents_created": created,
        }

    # -- 7. tesis externas (sin paywalls) -----------------------------------------
    def _collect_external_theses(self, db: Session, company: Company) -> dict[str, Any]:
        rows = list(
            db.scalars(
                select(Document)
                .where(
                    Document.company_id == company.id,
                    Document.source_type == "external_thesis",
                )
                .order_by(desc(Document.id))
                .limit(10)
            ).all()
        )
        if not rows:
            return _pending(
                "tesis externas",
                "Sin tesis de terceros (no se scrapean paywalls).",
                action=EXTERNAL_THESIS_HOWTO,
            )
        return {
            "status": "ok",
            "source": "tesis externas (pegadas por el usuario)",
            "items": [{"title": r.title, "url": r.source_url} for r in rows],
        }

    # -- helpers de persistencia ---------------------------------------------------
    def _get_or_create_document(
        self, db: Session, company: Company, *, title: str, source_type: str, source_url: str
    ) -> Document:
        existing = db.scalar(
            select(Document).where(
                Document.company_id == company.id,
                Document.source_type == source_type,
                Document.title == title,
            )
        )
        if existing:
            return existing
        document = Document(
            company_id=company.id,
            title=title,
            source_type=source_type,
            source_url=source_url,
            metadata_={"provider": source_type, "auto_ingested": True},
        )
        db.add(document)
        db.flush()
        return document

    def _replace_facts(self, db: Session, company: Company, source_type: str) -> None:
        tenant_id = db.info.get("tenant_id")
        tenant_filter = (
            FinancialFact.tenant_id == tenant_id
            if tenant_id is not None
            else FinancialFact.tenant_id.is_(None)
        )
        for fact in db.scalars(
            select(FinancialFact).where(
                FinancialFact.company_id == company.id,
                FinancialFact.source_type == source_type,
                tenant_filter,
            )
        ).all():
            db.delete(fact)
        db.flush()
