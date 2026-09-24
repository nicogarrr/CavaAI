"""Thesis generation with evidence fingerprinting and honest insufficient-data handling."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    FinancialFact,
    MarketPrice,
    SourceAudit,
    ThesisVersion,
)
from app.services.source_auditor import SourceAuditor
from app.services.source_hierarchy_service import classify_source
from app.services.long_term_model_service import LongTermModelService
from app.services.valuation_service import ValuationService
from app.valuation.engines.base import MODEL_VERSION
from app.valuation.financial_snapshot import FinancialSnapshotBuilder
from app.valuation.moat_framework import empty_moat_framework
from app.services.company_resolver import resolve_company

PROMPT_VERSION = "thesis-render-v2"


class ThesisService:
    def __init__(self) -> None:
        self.valuation_service = ValuationService()
        self.auditor = SourceAuditor()

    def data_freshness(self, db: Session, company_id: int) -> datetime | None:
        """Marca temporal del dato mas reciente que alimenta una tesis.

        Mira hechos financieros, precios, noticias y documentos de la empresa;
        si alguno es posterior a thesis.created_at, la version esta obsoleta
        (stale) y conviene regenerar.
        """
        from app.models import Document, FinancialFact, MarketPrice, NewsEvent

        latest_seen: datetime | None = None
        for model in (FinancialFact, MarketPrice, NewsEvent, Document):
            stamp = db.scalar(
                select(func.max(model.updated_at)).where(model.company_id == company_id)
            )
            if stamp is not None and (latest_seen is None or stamp > latest_seen):
                latest_seen = stamp
        return latest_seen

    def latest(self, db: Session, ticker: str) -> ThesisVersion | None:
        company = resolve_company(db, ticker)
        if not company:
            return None
        return db.scalar(
            select(ThesisVersion)
            .where(ThesisVersion.company_id == company.id)
            .order_by(desc(ThesisVersion.version))
            .limit(1)
        )

    def _input_fingerprint(
        self,
        db: Session,
        company: Company,
        valuation: dict,
        long_term_model: dict,
    ) -> str:
        documents = list(
            db.execute(
                select(Document.id, Document.checksum, Document.updated_at)
                .where(Document.company_id == company.id)
                .order_by(Document.id)
            ).all()
        )
        facts = list(
            db.execute(
                select(
                    FinancialFact.id,
                    FinancialFact.metric,
                    FinancialFact.period,
                    FinancialFact.value,
                )
                .where(FinancialFact.company_id == company.id)
                .order_by(FinancialFact.id)
            ).all()
        )
        market_price = db.scalar(
            select(MarketPrice)
            .where(MarketPrice.company_id == company.id)
            .order_by(desc(MarketPrice.date))
            .limit(1)
        )
        payload = {
            "documents": [f"{d.id}:{d.checksum or d.updated_at.isoformat()}" for d in documents],
            "facts": [f"{f.id}:{f.metric}:{f.period}:{f.value}" for f in facts],
            "market_price": (
                f"{market_price.date.isoformat()}:{market_price.close}" if market_price else None
            ),
            "model_version": MODEL_VERSION,
            "prompt_version": PROMPT_VERSION,
            "valuation_status": valuation.get("status"),
            "engine": (valuation.get("trace") or {}).get("engine"),
            "input_source": (valuation.get("trace") or {}).get("input_source"),
            "fundamental_model_fingerprint": (
                long_term_model.get("persistence") or {}
            ).get("input_fingerprint"),
            "fundamental_model_status": long_term_model.get("status"),
            "missing_mandatory_drivers": long_term_model.get(
                "missing_mandatory_drivers"
            ),
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def generate(
        self,
        db: Session,
        ticker: str,
        force_new_version: bool = False,
        phase_callback=None,
    ) -> ThesisVersion:
        """Persist model, valuation, thesis, evidence, graph and red team atomically.

        phase_callback(name) fires when generation ACTUALLY enters each real
        phase (async job progress; never synthetic progress).

        Todo el trabajo ocurre en un SAVEPOINT: un fallo revierte solo lo
        escrito por esta generación (nunca ``db.rollback()`` global, que
        descartaría trabajo ajeno pendiente en la sesión).
        """
        savepoint = db.begin_nested()
        try:
            thesis = self._generate_atomic(
                db, ticker, force_new_version, phase_callback, savepoint=savepoint
            )
        except Exception:
            savepoint.rollback()
            raise
        return thesis

    def _generate_atomic(
        self,
        db: Session,
        ticker: str,
        force_new_version: bool = False,
        phase_callback=None,
        savepoint=None,
    ) -> ThesisVersion:
        def _phase(name: str) -> None:
            if phase_callback is not None:
                phase_callback(name)

        company = resolve_company(db, ticker)
        if not company:
            raise ValueError(f"Unknown ticker: {ticker}")

        # Auto-ingesta best-effort (ley: ninguna tesis insufficient_data si la
        # empresa tiene filings): SEC companyfacts + Finnhub quote/profile +
        # filings/news/earnings/IR/tesis. Nunca rompe la generacion.
        _phase("collect_evidence")
        evidence: dict = {}
        try:
            from app.services.thesis_evidence_service import ThesisEvidenceService

            evidence = ThesisEvidenceService().collect(db, company) or {}
        except Exception:
            evidence = {}

        _phase("build_fundamental_model")
        long_term_model = LongTermModelService().build(
            db, company, horizon=5, commit=False
        )
        _phase("run_valuation")
        valuation = self.valuation_service.value_company(db, company)
        missing_drivers = long_term_model.get("missing_mandatory_drivers") or []
        if missing_drivers:
            valuation["publishable"] = False
            valuation["missing_inputs"] = sorted(
                set((valuation.get("missing_inputs") or []) + missing_drivers)
            )
        valuation.setdefault("trace", {})["fundamental_model"] = {
            "model_version_id": (long_term_model.get("persistence") or {}).get(
                "model_version_id"
            ),
            "version": (long_term_model.get("persistence") or {}).get("version"),
            "framework": (long_term_model.get("framework") or {}).get("key"),
            "status": long_term_model.get("status"),
            "publishable": long_term_model.get("publishable"),
            "missing_mandatory_drivers": missing_drivers,
        }
        valuation["long_term_model"] = long_term_model
        fingerprint = self._input_fingerprint(db, company, valuation, long_term_model)

        existing = self.latest(db, ticker)
        if existing and not force_new_version:
            if getattr(existing, "input_fingerprint", None) == fingerprint:
                # Sin mutación previa: el fingerprint se calculó solo con
                # lecturas, así que se devuelve sin tocar la transacción
                # (el savepoint de generate() se libera solo).
                if savepoint is not None:
                    savepoint.rollback()
                return existing
            # Material evidence changed — fall through and create a new version.

        _phase("persist_valuation_snapshot")
        self.valuation_service.persist_output(db, company, valuation, commit=False)
        snapshot = FinancialSnapshotBuilder().build(db, company)
        facts = snapshot.facts

        _phase("source_audit")
        claims = self._build_claims(company, facts, valuation)
        audit = self.auditor.audit(
            claims=claims,
            calculation_trace=valuation.get("trace"),
            requires_sec_fmp_reconciliation=(valuation.get("trace") or {}).get("input_source")
            == "financial_facts",
        )

        previous = self.latest(db, ticker)
        version = (previous.version + 1) if previous else 1

        publishable = bool(valuation.get("publishable"))
        if valuation.get("status") == "insufficient_data":
            status = "insufficient_data"
        elif valuation.get("status") == "partial":
            # Rango indicativo con precio: parcial-publicable, nunca final.
            status = "draft_failed_audit" if not audit.passed else "draft"
        elif not audit.passed:
            status = "draft_failed_audit"
        elif publishable:
            status = "final"
        else:
            status = "draft"

        _phase("compose_thesis")
        hypothesis = self._hypothesis(company, valuation)
        catalysts = self._catalysts(evidence)
        invalidation = self._invalidation_criteria(company, valuation)
        scenario_probabilities = self._scenario_probabilities(long_term_model)

        summary = self._card_summary(company, valuation, hypothesis)
        thesis_markdown = self._render_markdown(
            company,
            valuation,
            audit.as_dict(),
            facts,
            long_term_model=long_term_model,
            version=version,
            evidence=evidence,
            hypothesis=hypothesis,
            catalysts=catalysts,
            invalidation_criteria=invalidation,
            scenario_probabilities=scenario_probabilities,
        )

        def _dec(value) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        _phase("persist_thesis")
        thesis = ThesisVersion(
            company_id=company.id,
            version=version,
            status=status,
            thesis_markdown=thesis_markdown,
            executive_summary=summary,
            rating=self._rating(
                valuation.get("margin_of_safety"),
                audit.passed,
                valuation.get("status"),
            ),
            current_price=_dec(valuation.get("current_price")),
            bear_value=_dec(valuation.get("bear_value")),
            base_value=_dec(valuation.get("base_value")),
            bull_value=_dec(valuation.get("bull_value")),
            expected_value=_dec(valuation.get("expected_value")),
            margin_of_safety=_dec(valuation.get("margin_of_safety")),
            data_confidence_score=self._confidence_score(valuation, facts),
            source_coverage_score=audit.source_coverage_score,
            red_team_score=0,
            valuation_risk_score=75 if "speculative" in (company.factor_tags or []) else 45,
            input_fingerprint=fingerprint,
            hypothesis=hypothesis,
            catalysts=catalysts,
            invalidation_criteria=invalidation,
            scenario_probabilities=scenario_probabilities,
        )
        db.add(thesis)
        db.flush()
        self._persist_claims(db, company, thesis, claims)
        db.add(
            SourceAudit(
                thesis_version_id=thesis.id,
                passed=audit.passed and publishable,
                source_coverage_score=audit.source_coverage_score,
                unsupported_claims=audit.unsupported_claims,
                weak_claims=audit.weak_claims,
                data_conflicts=audit.data_conflicts,
                required_fixes=audit.required_fixes
                + (
                    [f"Missing valuation inputs: {', '.join(valuation.get('missing_inputs') or [])}"]
                    if valuation.get("missing_inputs")
                    else []
                ),
            )
        )
        db.flush()
        from app.services.red_team_service import RedTeamService
        from app.services.thesis_graph_service import ThesisGraphService

        ThesisGraphService().build(db, company, thesis, commit=False)
        RedTeamService().run(db, company, thesis, commit=False)
        db.commit()
        db.refresh(thesis)
        # Human-in-the-loop mínimo viable: si TELEGRAM_APPROVAL_ENABLED, envía
        # el mensaje con botones inline. Best-effort: nunca rompe la generación.
        try:
            from app.services.thesis_approval_service import (
                maybe_request_thesis_approval,
            )

            maybe_request_thesis_approval(db, thesis, company.ticker)
        except Exception:
            pass
        return thesis

    def _persist_claims(
        self,
        db: Session,
        company: Company,
        thesis: ThesisVersion,
        claims: list[dict],
    ) -> None:
        for payload in claims:
            if not payload.get("material", True):
                continue
            statement = str(payload.get("claim") or "").strip()
            if not statement:
                continue
            source_id = payload.get("source_id")
            source_type = str(payload.get("source_type") or "unknown")
            claim = Claim(
                company_id=company.id,
                thesis_version_id=thesis.id,
                statement=statement,
                claim_type=str(payload.get("predicate") or "generated_thesis"),
                status="supported" if source_id else "unverified",
                confidence=Decimal(str(payload.get("confidence", 0.5))),
                materiality_score=8,
                source_quality=classify_source(source_type).key,
                created_by="thesis_generation",
                metadata_={
                    "generated_claim_id": payload.get("claim_id"),
                    "verification_state": payload.get(
                        "verification_state", "unverified"
                    ),
                    "prompt_version": PROMPT_VERSION,
                },
            )
            db.add(claim)
            db.flush()
            if source_id:
                db.add(
                    ClaimEvidence(
                        claim_id=claim.id,
                        document_id=int(source_id),
                        evidence_type="supports",
                        summary=f"Generated from {source_type} source.",
                        confidence=claim.confidence,
                        source_tier=classify_source(source_type).key,
                        metadata_={"automatic": True, "generator": PROMPT_VERSION},
                    )
                )

    def _confidence_score(self, valuation: dict, facts: dict) -> int:
        if valuation.get("status") == "insufficient_data":
            return 15
        if not facts:
            return 25
        if valuation.get("publishable"):
            return 85
        return 55


    def _hypothesis(self, company: Company, valuation: dict) -> str:
        """Hipotesis comprobable derivada solo de datos del modelo (nunca inventada)."""
        price = valuation.get("current_price")
        base = valuation.get("base_value")
        mos = valuation.get("margin_of_safety")
        if price is None or base is None or mos is None:
            return (
                "Hipotesis en formacion: faltan datos de mercado o de valoracion "
                "para formular una hipotesis comprobable."
            )
        reverse = valuation.get("reverse_dcf") or {}
        required_growth = reverse.get("required_revenue_growth")
        growth_txt = (
            f" El reverse DCF exige un crecimiento de ingresos del {required_growth:.1%} anual."
            if required_growth is not None
            else ""
        )
        if mos >= 0:
            return (
                f"A {price:.2f}, el mercado valora {company.name} un {mos:.0%} por debajo "
                f"del escenario base ({base:.2f}). Hipotesis: los fundamentales modelados "
                f"son alcanzables y el mercado corrige ese descuento.{growth_txt}"
            )
        return (
            f"A {price:.2f}, el mercado valora {company.name} un {abs(mos):.0%} por encima "
            f"del escenario base ({base:.2f}). Hipotesis: el precio descuenta mas de lo "
            f"que los fundamentales modelados soportan.{growth_txt}"
        )

    def _catalysts(self, evidence: dict) -> list[dict]:
        """Catalizadores con fecha conocida (hoy: calendario de resultados)."""
        sources = (evidence or {}).get("sources") or {}
        earnings = sources.get("earnings") or {}
        catalysts: list[dict] = []
        if earnings.get("status") == "ok" and earnings.get("next_date"):
            item: dict = {
                "label": "Proximos resultados",
                "date": earnings.get("next_date"),
                "source": "earnings_calendar",
            }
            if earnings.get("time"):
                item["time"] = earnings["time"]
            if earnings.get("eps_forecast") is not None:
                item["eps_forecast"] = earnings["eps_forecast"]
            catalysts.append(item)
        return catalysts

    def _invalidation_criteria(self, company: Company, valuation: dict) -> list[str]:
        """Condiciones observables que invalidarian la tesis, derivadas del modelo."""
        criteria: list[str] = []
        mos = valuation.get("margin_of_safety")
        base = valuation.get("base_value")
        if mos is not None and base is not None and mos >= 0:
            criteria.append(
                f"El precio supera de forma sostenida el valor base ({base:.2f}): "
                "el margen de seguridad desaparece."
            )
        reverse = valuation.get("reverse_dcf") or {}
        required_growth = reverse.get("required_revenue_growth")
        if required_growth is not None:
            criteria.append(
                f"Los ingresos reales se desvian de forma persistente del "
                f"{required_growth:.1%} anual que exige el reverse DCF."
            )
        moat = valuation.get("moat") or {}
        declining = [
            str(item.get("type"))
            for item in (moat.get("moats") or [])
            if item.get("trend") == "declining" and item.get("type")
        ]
        if declining:
            criteria.append(f"Deterioro confirmado del moat: {', '.join(declining)}.")
        if not criteria:
            criteria.append(
                "Tesis en formacion: sin criterios automaticos hasta completar la valoracion."
            )
        return criteria

    def _scenario_probabilities(self, long_term_model: dict) -> dict | None:
        """Probabilidades por escenario persistidas por el motor de modelado."""
        scenarios = (long_term_model or {}).get("scenarios") or {}
        probabilities = {
            name: scenario.get("probability")
            for name, scenario in scenarios.items()
            if isinstance(scenario, dict) and scenario.get("probability") is not None
        }
        return probabilities or None

    def _rating(self, margin_of_safety: float | None, audit_passed: bool, status: str | None) -> str:
        if status == "insufficient_data":
            return "insufficient_data"
        if not audit_passed:
            return "blocked"
        if margin_of_safety is None:
            return "incomplete_price"
        if margin_of_safety > 0.30:
            return "attractive"
        if margin_of_safety < -0.20:
            return "expensive"
        return "watch"

    def _card_summary(self, company: Company, valuation: dict, hypothesis: str) -> str:
        """Resumen de la tarjeta "Ultima tesis": legible y en el idioma de la UI.

        La hipotesis ya se deriva solo de datos del modelo (nunca inventada);
        los estados incompletos anaden su salvedad honesta en castellano.
        El detalle de motor (bucket/engine) vive en el memo completo, no en
        la tarjeta.
        """
        if valuation.get("status") == "insufficient_data":
            missing = ", ".join(valuation.get("missing_inputs") or []) or "datos financieros basicos"
            return (
                f"Tesis de {company.ticker} no publicable todavia: faltan {missing}. "
                "Ningun valor justo debe considerarse fiable hasta completar las fuentes."
            )
        if valuation.get("status") == "partial":
            missing = ", ".join(valuation.get("missing_inputs") or []) or "algunos inputs"
            return (
                f"{hypothesis} Valoracion parcial-indicativa: "
                f"faltan {missing} (ver seccion 13 del memo)."
            )
        return hypothesis

    def _executive_summary(self, company: Company, valuation: dict) -> str:
        source = (valuation.get("trace") or {}).get("input_source", "unknown")
        engine = (valuation.get("trace") or {}).get("engine", "unknown")
        if valuation.get("status") == "insufficient_data":
            missing = ", ".join(valuation.get("missing_inputs") or []) or "required financial inputs"
            return (
                f"{company.ticker} valuation is NOT PUBLISHABLE ({engine}). "
                f"Missing: {missing}. No fair value should be trusted until inputs are sourced."
            )
        if valuation.get("status") == "partial":
            missing = ", ".join(valuation.get("missing_inputs") or []) or "remaining inputs"
            return (
                f"{company.ticker} valuation is PARTIAL-INDICATIVE ({engine}): "
                f"bear/base/bull range and reverse DCF computed from documented fallback "
                f"assumptions (see section 13). Still missing: {missing}. Not a final fair value."
            )
        return (
            f"{company.ticker} is in the {company.company_type} bucket (engine={engine}). "
            f"Valuation input source: {source}. "
            "This version uses deterministic valuation traces and source-audited claims."
        )

    def _build_claims(
        self,
        company: Company,
        facts: dict[str, FinancialFact],
        valuation: dict,
    ) -> list[dict]:
        """Build structured claims. Metadata is non-material; facts are material."""
        claims: list[dict] = []

        # Non-material metadata — must not gate the audit as unsupported "financial" claims.
        claims.append(
            {
                "claim_id": f"{company.ticker}:company_type",
                "subject": company.ticker,
                "predicate": "company_type",
                "object": company.company_type,
                "claim": f"{company.ticker} is tracked as {company.company_type}.",
                "source_id": None,
                "source_type": "company_master",
                "confidence": 1.0,
                "material": False,
                "materiality": "metadata",
                "verification_state": "internal",
            }
        )
        claims.append(
            {
                "claim_id": f"{company.ticker}:valuation_model",
                "subject": company.ticker,
                "predicate": "valuation_model",
                "object": company.valuation_model,
                "claim": f"Valuation method selected: {company.valuation_model}.",
                "source_id": None,
                "source_type": "company_master",
                "confidence": 1.0,
                "material": False,
                "materiality": "metadata",
                "verification_state": "internal",
            }
        )

        for metric, fact in facts.items():
            claims.append(
                {
                    "claim_id": f"{company.ticker}:{metric}:{fact.period}",
                    "subject": company.ticker,
                    "predicate": metric,
                    "object": float(fact.value),
                    "unit": fact.unit,
                    "period": fact.period,
                    "claim": f"{company.ticker} {metric} is {fact.value} for {fact.period}.",
                    "source_id": fact.source_id,
                    "source_type": fact.source_type,
                    "source_document_id": fact.source_id,
                    "confidence": float(fact.confidence),
                    "material": metric
                    in {"revenue", "free_cash_flow", "net_debt", "shares_diluted", "fcf_margin"},
                    "materiality": "high"
                    if metric in {"revenue", "free_cash_flow", "shares_diluted"}
                    else "medium",
                    "verification_state": "reported" if fact.is_reported else "derived",
                }
            )

        if valuation.get("status") == "insufficient_data":
            claims.append(
                {
                    "claim_id": f"{company.ticker}:valuation_blocked",
                    "subject": company.ticker,
                    "predicate": "valuation_status",
                    "object": "insufficient_data",
                    "claim": (
                        f"{company.ticker} fair value is blocked pending: "
                        f"{', '.join(valuation.get('missing_inputs') or [])}."
                    ),
                    "source_id": None,
                    "source_type": "valuation_engine",
                    "confidence": 1.0,
                    "material": False,
                    "materiality": "process",
                    "verification_state": "system",
                }
            )

        assumed = (valuation.get("trace") or {}).get("assumed")
        if (valuation.get("trace") or {}).get("valuation_basis") == "indicative_assumptions" and assumed:
            claims.append(
                {
                    "claim_id": f"{company.ticker}:indicative_assumptions",
                    "subject": company.ticker,
                    "predicate": "valuation_assumptions",
                    "object": "indicative",
                    "claim": (
                        f"{company.ticker} indicative range assumes "
                        f"FCF margin base {assumed.get('fcf_margin_base')} "
                        f"(band {assumed.get('fcf_margin_band')})"
                        + (
                            " and $1 revenue floor"
                            if assumed.get("revenue_floor_used")
                            else ""
                        )
                        + "; not reported facts."
                    ),
                    "source_id": None,
                    "source_type": "valuation_engine",
                    "confidence": 1.0,
                    "material": False,
                    "materiality": "process",
                    "verification_state": "assumption",
                }
            )

        return claims

    def _facts_markdown(self, facts: dict[str, FinancialFact]) -> str:
        if not facts:
            return (
                "No coherent financial snapshot is available. "
                "Ingest SEC/FMP facts before any publishable valuation."
            )
        rows = [
            "| Metric | Value | Unit | Period | Source |",
            "| --- | ---: | --- | --- | --- |",
        ]
        for metric, fact in facts.items():
            rows.append(
                f"| {metric} | {fact.value} | {fact.unit} | {fact.period} | "
                f"{fact.source_type} #{fact.source_id or 'n/a'} |"
            )
        return "\n".join(rows)

    def _valuation_markdown(self, valuation: dict) -> str:
        if valuation.get("status") == "insufficient_data":
            missing = "\n".join(f"- {item}" for item in (valuation.get("missing_inputs") or []))
            return (
                "**NO VALUATION — insufficient data**\n\n"
                f"Engine: `{(valuation.get('trace') or {}).get('engine', 'unknown')}`\n\n"
                f"Missing:\n{missing or '- required inputs'}\n\n"
                "CavaAI will not publish a fair value from bootstrap assumptions."
            )

        if valuation.get("status") == "partial":
            trace = valuation.get("trace") or {}
            assumed = trace.get("assumed") or {}
            missing = "\n".join(f"- {item}" for item in (valuation.get("missing_inputs") or []))
            supuestos = (
                f"FCF margin base {assumed.get('fcf_margin_base')} "
                f"(band {assumed.get('fcf_margin_band')})"
                + ("; $1 revenue floor (no coherent revenue)" if assumed.get("revenue_floor_used") else "")
                + f"; revenue growth {assumed.get('revenue_growth')}"
                + f"; WACC {assumed.get('wacc')}"
                + f"; terminal {assumed.get('terminal_growth')}"
            )
            return (
                "**PARTIAL-INDICATIVE RANGE — not a final fair value**\n\n"
                f"Engine: `{trace.get('engine', 'unknown')}` "
                f"(basis: `{trace.get('valuation_basis', 'indicative_assumptions')}`).\n\n"
                f"{self._range_lines(valuation)}\n\n"
                f"Documented assumptions (NOT reported facts): {supuestos}.\n\n"
                f"Reverse DCF vs market price: see section 14.\n\n"
                f"Still missing before publishing:\n{missing or '- none listed'}\n\n"
                f"{trace.get('notice', '')}"
            )

        return "\n".join(
            [
                f"- Status: `{valuation.get('status')}` publishable={valuation.get('publishable')}",
                *self._range_lines(valuation).split("\n"),
                f"- Input source: {(valuation.get('trace') or {}).get('input_source', 'unknown')}",
                f"- Engine: {(valuation.get('trace') or {}).get('engine', 'unknown')}",
            ]
        )

    def _range_lines(self, valuation: dict) -> str:
        price = valuation.get("current_price")
        mos = valuation.get("margin_of_safety")
        price_txt = f"{price:.2f}" if price is not None else "N/A (no market price)"
        mos_txt = f"{mos:.1%}" if mos is not None else "N/A (requires market price)"

        def fmt(v):
            return f"{v:.2f}" if v is not None else "N/A"

        return "\n".join(
            [
                f"- Current price: {price_txt}",
                f"- Bear value: {fmt(valuation.get('bear_value'))}",
                f"- Base value: {fmt(valuation.get('base_value'))}",
                f"- Bull value: {fmt(valuation.get('bull_value'))}",
                f"- Expected value: {fmt(valuation.get('expected_value'))}",
                f"- Margin of safety: {mos_txt}",
            ]
        )

    def _moat_markdown(self, company: Company, valuation: dict) -> str:
        moat = valuation.get("moat") or empty_moat_framework(
            company.company_type, company.factor_tags or [], company.special_risks or []
        )
        lines = [
            moat.get("note", "Requires sourced evidence before final qualitative claims."),
            "",
            "| Type | Strength | Trend | Confidence | Status |",
            "| --- | ---: | --- | ---: | --- |",
        ]
        for item in moat.get("moats") or []:
            lines.append(
                f"| {item.get('type')} | {item.get('strength', 0):.2f} | {item.get('trend')} | "
                f"{item.get('confidence', 0):.2f} | {item.get('status')} |"
            )
        return "\n".join(lines)

    def _earnings_markdown(self, sources: dict) -> str:
        earnings = sources.get("earnings") or {}
        transcript = sources.get("transcript") or {}
        lines = [
            "Call claims are stored separately and later verified against reported outcomes."
        ]
        if earnings.get("status") == "ok":
            extra = f" {earnings['time']}" if earnings.get("time") else ""
            eps = earnings.get("eps_forecast")
            eps_txt = f", EPS forecast {eps}" if eps is not None else ""
            lines.append(f"Next earnings: {earnings.get('next_date')}{extra}{eps_txt}.")
        else:
            lines.append(
                f"Next earnings: pendiente ({earnings.get('detail', 'sin fecha de earnings')})."
            )
            if earnings.get("action"):
                lines.append(f"Accion: {earnings['action']}")
        if transcript.get("status") == "ok":
            lines.append(
                f"Latest transcript: {transcript.get('title')} ({transcript.get('period')})."
            )
        else:
            lines.append(
                f"Transcripcion: {transcript.get('detail', 'pendiente transcripcion')}."
            )
            if transcript.get("action"):
                lines.append(f"Accion: {transcript['action']}")
        return "\n".join(lines)

    def _news_markdown(self, sources: dict) -> str:
        news = sources.get("news") or {}
        base = (
            "Material news updates require source audit and human approval "
            "before thesis versioning."
        )
        items = news.get("items") or []
        if not items:
            pending = news.get("detail", "sin noticias ingeridas")
            action = f" Accion: {news['action']}" if news.get("action") else ""
            return f"{base}\nLatest material news: pendiente ({pending}).{action}"
        rows = [base, "", "Latest material news:"]
        for item in items:
            rows.append(
                f"- {item.get('date', '?')} [{item.get('source', '?')}] "
                f"{item.get('title', '')} (materiality {item.get('materiality', '?')})"
            )
        return "\n".join(rows)

    def _sources_markdown(self, sources: dict) -> str:
        ok: list[str] = ["- Company master seed"]
        pending: list[str] = []
        labels = {
            "fundamentals": "Fundamentals",
            "market": "Market price/profile",
            "filings": "Filings 10-K/10-Q/8-K",
            "news": "News",
            "earnings": "Earnings date",
            "transcript": "Transcript",
            "ir": "Investor-relations",
            "external_theses": "Tesis externas",
        }
        for key, label in labels.items():
            block = sources.get(key) or {}
            if block.get("status") == "ok":
                detail = self._source_ok_detail(key, block)
                ok.append(f"- {label}: conseguido ({detail})")
            else:
                reason = block.get("detail", "pendiente") if block else "no intentado"
                action = f" | Accion: {block['action']}" if block.get("action") else ""
                pending.append(f"- {label}: pendiente ({reason}){action}")
        lines = ["Conseguido:"] + ok
        if pending:
            lines += ["", "Pendiente:"] + pending
        return "\n".join(lines)

    def _source_ok_detail(self, key: str, block: dict) -> str:
        if key == "fundamentals":
            metrics = ", ".join(block.get("metrics") or [])
            return f"{block.get('source')}, {block.get('facts_imported')} facts: {metrics}"
        if key == "market":
            parts = []
            if block.get("price") is not None:
                parts.append(f"price {block['price']}")
            if block.get("market_cap") is not None:
                parts.append(f"market cap {block['market_cap']:.0f}")
            if block.get("name"):
                parts.append(f"name '{block['name']}'")
            return f"{block.get('source')}" + (f": {', '.join(parts)}" if parts else "")
        if key == "filings":
            forms = ", ".join(
                f"{i.get('form')} {i.get('filing_date')}" for i in (block.get("items") or [])
            )
            return f"{block.get('source')}: {forms}"
        if key == "news":
            return f"{len(block.get('items') or [])} eventos materiales"
        if key == "earnings":
            return f"next {block.get('next_date')}"
        if key == "transcript":
            return f"{block.get('title')} ({block.get('period')})"
        if key == "ir":
            titles = "; ".join(
                str(i.get("title") or "") for i in (block.get("items") or [])[:3]
            )
            return f"{block.get('source')}: {len(block.get('items') or [])} releases ({titles})"
        if key == "external_theses":
            return f"{len(block.get('items') or [])} tesis pegadas"
        return str(block.get("source") or "ok")

    def _render_markdown(
        self,
        company: Company,
        valuation: dict,
        audit: dict,
        facts: dict[str, FinancialFact],
        *,
        long_term_model: dict,
        version: int,
        evidence: dict | None = None,
        hypothesis: str | None = None,
        catalysts: list | None = None,
        invalidation_criteria: list | None = None,
        scenario_probabilities: dict | None = None,
    ) -> str:
        reverse = valuation.get("reverse_dcf") or {}
        required_growth = reverse.get("required_revenue_growth")
        reverse_line = (
            f"Required revenue growth: {required_growth:.1%}"
            if required_growth is not None
            else "Reverse DCF unavailable (missing market price or valuation inputs)."
        )
        scenario_style = (valuation.get("trace") or {}).get("scenario_style", "n/a")
        framework = long_term_model.get("framework") or {}
        mandatory_missing = long_term_model.get("missing_mandatory_drivers") or []
        market_opportunity = long_term_model.get("market_opportunity") or {}
        evidence = evidence or {}
        sources = evidence.get("sources") or {}
        hypothesis = hypothesis or self._hypothesis(company, valuation)
        catalysts = catalysts if catalysts is not None else self._catalysts(evidence)
        invalidation_criteria = (
            invalidation_criteria
            if invalidation_criteria is not None
            else self._invalidation_criteria(company, valuation)
        )
        scenario_probabilities = (
            scenario_probabilities
            if scenario_probabilities is not None
            else self._scenario_probabilities(long_term_model)
        )
        probabilities_line = (
            "Probabilities (model): "
            + " · ".join(f"{name} {prob:.0%}" for name, prob in scenario_probabilities.items())
            if scenario_probabilities
            else "Probabilities: pendiente (el modelo no las ha persistido)."
        )
        catalysts_lines = "\n".join(
            f"- {item.get('label')}: {item.get('date')}"
            + (f" {item.get('time')}" if item.get('time') else "")
            + (f" (EPS forecast {item.get('eps_forecast')})" if item.get("eps_forecast") is not None else "")
            for item in catalysts
        ) or "- Sin catalizadores con fecha conocida; pendiente del calendario de resultados."
        invalidation_lines = "\n".join(f"- {criterion}" for criterion in invalidation_criteria)

        return f"""# {company.ticker} Thesis v{version}

## 1. Executive Summary
{company.name} is tracked as `{company.company_type}` with model `{company.valuation_model}`.
Valuation input source: `{(valuation.get("trace") or {}).get("input_source", "unknown")}`.
Engine: `{(valuation.get("trace") or {}).get("engine", "unknown")}`.

## 2. Hypothesis
{hypothesis}
The investable question is whether the evidence supports the assumptions behind the selected model, not whether a model output looks attractive in isolation.

## 3. Business Model
Sector: {company.sector}. Industry: {company.industry}.
Company-specific framework: `{framework.get("key", "unknown")}`. Primary question: {framework.get("primary_question", "unknown")}.
Mandatory drivers missing: {", ".join(mandatory_missing) if mandatory_missing else "none"}.

## 4. Latest Results
{self._facts_markdown(facts)}

## 5. Historical Financials
Stored in `financial_facts` and `financial_statements` once ingested. Snapshot builder enforces period coherence.

## 6. Free Cash Flow
Derived only from coherent snapshot facts (same fiscal anchor). Bootstrap FCF margins are disabled.

## 7. Balance Sheet
Net debt / cash / shares must align with the income-statement anchor period (or a compatible instant).

## 8. Capital Allocation
Tracked through filings, calls, buybacks, dilution and dividends. Funding-gap dilution replaces fixed $100 capital raises when cash/capex facts exist.

## 9. Management And Calls
{self._earnings_markdown(sources)}

## 10. News And Catalysts
{catalysts_lines}
{self._news_markdown(sources)}

## 11. Risks
{", ".join(company.special_risks)}

## 12. Competition And Moat
{self._moat_markdown(company, valuation)}

## 13. Valuation
{self._valuation_markdown(valuation)}

### Long-Term Fundamental Modeling Engine
Persisted model version: `{(long_term_model.get("persistence") or {}).get("version")}`.
Model status: `{long_term_model.get("status")}`. Market-opportunity verdict: `{(market_opportunity.get("verdict") or {}).get("label", "unknown")}`.

## 14. Reverse DCF
{reverse_line}

## 15. Bear / Base / Bull
Scenario style: `{scenario_style}`. {probabilities_line}

## 16. Red Team
Primary red-team question: what assumption would break first if the next filing contradicts the current model?

## 17. What Would Invalidate The Thesis
{invalidation_lines}
Structural invalidators: unsupported claims, missing calculation traces, adverse primary filings, incoherent snapshots, or material assumption drift.

## 18. What To Watch
{", ".join(company.special_sources)}

## 19. Source Audit
Passed: {audit["passed"]}
Coverage score: {audit["source_coverage_score"]}
Unsupported claims: {audit["unsupported_claims"]}

## 20. Sources
{self._sources_markdown(sources)}
Fingerprint: evidence-set hash drives versioning.
"""
