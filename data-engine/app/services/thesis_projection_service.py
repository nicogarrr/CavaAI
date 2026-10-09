"""Proyeccion determinista de tesis a 5 ejercicios (PR A: sin LLM).

Todo numero sale de calculo sobre datos ya persistidos: facts anuales
oficiales (SEC/ESEF), asunciones de driver versionadas, ValuationAssumption e
InferredInput. Si falta un input critico la salida es N/D explicito: nunca un
0 ni un valor por defecto silencioso. El precio objetivo a 5 anos se apoya en
ValuationService (no se reimplementa el DCF) y se rotula INFERIDO por ser
proyeccion propia. La capa LLM (PR B) consume este contrato; aqui no se llama
a ningun modelo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.models import (
    Company,
    Document,
    DriverAssumptionVersion,
    FinancialFact,
    FundamentalDriver,
    ThesisProjectionYear,
    ValuationAssumption,
    ValuationModel,
    ValuationOutput,
)
from app.services.inferred_input_service import InferredInputService
from app.services.valuation_service import (
    ValuationService,
    _position_price,
    _position_price_as_of,
)
from app.valuation.engines.base import margin_of_safety
from app.valuation.point_in_time import (
    assert_fiscal_year_no_lookahead,
    assert_no_lookahead,
)

MODEL_TYPE = "thesis_5y"
MODEL_VERSION = "thesis-projection-v1"
HORIZON_YEARS = 5
SCENARIOS = ("bear", "base", "bull")

LABEL_OFICIAL = "OFICIAL"
LABEL_INFERIDO = "INFERIDO"
LABEL_ND = "N/D"

DISCLAIMER_ES = (
    "Proyeccion del modelo a 5 ejercicios basada en hipotesis propias "
    "(INFERIDO): no es un dato oficial ni una recomendacion de inversion. "
    "Las decisiones de inversion son responsabilidad del usuario."
)

# Facts cuya fuente es un regulador/filing oficial. Un proveedor de datos
# (FMP, seed) NO es OFICIAL: se etiqueta INFERIDO con su fuente nombrada.
OFFICIAL_FACT_SOURCES = frozenset({"SEC", "ESEF"})

# Dispersion de escenarios (politica del modelo): los mismos anchos que
# mechanical_dcf_scenarios para no inventar una segunda convencion.
GROWTH_SPREAD = 0.08
MARGIN_SPREAD = 0.06
MARGIN_CAP = 0.45

# Cuota diaria de recalculos persistidos por tenant (POST). El GET es
# calculo puro y no consume cuota.
DAILY_RECALC_QUOTA = 10

GROWTH_KEY = "revenue_growth"
MARGIN_KEY = "fcf_margin"
ANNUAL_METRICS = ("revenue", "free_cash_flow", "net_income", "shares_diluted")


class ProjectionQuotaExceeded(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"cuota diaria de {limit} recalculos agotada")
        self.limit = limit


@dataclass(frozen=True)
class FactBase:
    """Ultimo dato anual conocido de una metrica, con su procedencia."""

    value: float | None
    fiscal_year: int | None
    label: str
    source: str | None
    source_url: str | None
    source_date: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valor": self.value,
            "ejercicio": self.fiscal_year,
            "etiqueta": self.label,
            "fuente": self.source,
            "fuente_url": self.source_url,
            "fuente_fecha": self.source_date,
        }


@dataclass(frozen=True)
class RateAssumption:
    """Crecimiento o margen aplicable a un ejercicio/escenario."""

    value: float | None
    label: str
    base: str | None
    source_urls: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "valor": self.value,
            "etiqueta": self.label,
            "base": self.base,
        }
        if self.source_urls:
            out["source_urls"] = list(self.source_urls)
        return out


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


class ThesisProjectionService:
    """Proyeccion anual bear/base/bull a ``HORIZON_YEARS`` ejercicios."""

    # -- facts anuales ------------------------------------------------------

    def _annual_facts(
        self, db: Session, company: Company, as_of: date
    ) -> dict[str, dict[int, FinancialFact]]:
        """Ultimo fact anual por metrica y ejercicio, sin lookahead.

        Un fact de un ejercicio fiscal posterior al corte levanta
        LookaheadError (misma politica estricta que
        HistoricalValuationService): proyectar con datos del futuro no es una
        proyeccion, es una trampa.
        """
        rows = db.scalars(
            select(FinancialFact)
            .where(
                FinancialFact.company_id == company.id,
                FinancialFact.metric.in_(ANNUAL_METRICS),
                FinancialFact.fiscal_year.is_not(None),
            )
            .order_by(FinancialFact.fiscal_year, desc(FinancialFact.id))
        ).all()
        out: dict[str, dict[int, FinancialFact]] = {}
        for row in rows:
            assert_fiscal_year_no_lookahead(
                as_of=as_of,
                fiscal_year=row.fiscal_year,
                label=f"FinancialFact {company.ticker} {row.metric}",
            )
            if (row.fiscal_quarter or "").upper().startswith("Q"):
                continue
            # Ordenado por id descendente: el primero por ejercicio es el mas
            # reciente; setdefault conserva ese y descarta restatements viejos.
            out.setdefault(row.metric, {}).setdefault(row.fiscal_year, row)  # type: ignore[arg-type]
        return out

    def _fact_base(
        self, db: Session, facts: dict[str, dict[int, FinancialFact]], metric: str
    ) -> FactBase:
        by_year = facts.get(metric) or {}
        if not by_year:
            return FactBase(None, None, LABEL_ND, None, None, None)
        year = max(by_year)
        fact = by_year[year]
        label = (
            LABEL_OFICIAL
            if (fact.source_type or "") in OFFICIAL_FACT_SOURCES
            else LABEL_INFERIDO
        )
        url: str | None = None
        fecha: str | None = None
        detalle = fact.source_type or "desconocida"
        if fact.source_id:
            doc = db.get(Document, fact.source_id)
            if doc is not None:
                url = doc.source_url
                fecha = doc.published_at.date().isoformat() if doc.published_at else None
                detalle = f"{detalle} ({doc.title})" if doc.title else detalle
        return FactBase(
            _num(fact.value),
            year,
            label,
            f"{detalle} FY{year}",
            url,
            fecha,
        )

    # -- asunciones ----------------------------------------------------------

    def _driver_overrides(
        self, db: Session, company: Company
    ) -> dict[tuple[str, int, str], dict[str, Any]]:
        """Ultima version por (driver_key, ejercicio, escenario)."""
        rows = db.execute(
            select(DriverAssumptionVersion, FundamentalDriver.driver_key)
            .join(FundamentalDriver)
            .where(
                FundamentalDriver.company_id == company.id,
                FundamentalDriver.driver_key.in_((GROWTH_KEY, MARGIN_KEY)),
            )
            .order_by(DriverAssumptionVersion.id)
        ).all()
        out: dict[tuple[str, int, str], dict[str, Any]] = {}
        for version, driver_key in rows:
            out[(driver_key, version.fiscal_year, version.scenario)] = {
                "value": _num(version.value),
                "source": version.source,
                "user_override": version.user_override,
            }
        return out

    def _valuation_assumptions(
        self, db: Session, company: Company
    ) -> dict[tuple[str, str, int], ValuationAssumption]:
        rows = db.scalars(
            select(ValuationAssumption)
            .join(
                ValuationModel,
                ValuationAssumption.valuation_model_id == ValuationModel.id,
            )
            .where(
                ValuationModel.company_id == company.id,
                ValuationAssumption.name.in_((GROWTH_KEY, MARGIN_KEY)),
                ValuationAssumption.year.is_not(None),
            )
            .order_by(ValuationAssumption.id)
        ).all()
        out: dict[tuple[str, str, int], ValuationAssumption] = {}
        for row in rows:
            out[(row.name, row.scenario, row.year)] = row  # type: ignore[index]
        return out

    @staticmethod
    def _revenue_cagr(by_year: dict[int, FinancialFact]) -> RateAssumption:
        """CAGR de ingresos sobre la historia anual disponible (INFERIDO)."""
        points = sorted(
            (year, _num(fact.value))
            for year, fact in by_year.items()
            if _num(fact.value) is not None
        )
        if len(points) < 2:
            return RateAssumption(None, LABEL_ND, None)
        (first_year, first), (last_year, last) = points[0], points[-1]
        span = last_year - first_year
        if span < 1 or first is None or last is None or first <= 0:
            return RateAssumption(None, LABEL_ND, None)
        cagr = (last / first) ** (1 / span) - 1
        return RateAssumption(
            cagr,
            LABEL_INFERIDO,
            f"CAGR de ingresos FY{first_year}-FY{last_year} sobre facts anuales "
            f"({span} anos); la historia no garantiza el futuro",
        )

    def _growth(
        self,
        scenario: str,
        year: int,
        *,
        drivers: dict[tuple[str, int, str], dict[str, Any]],
        val_assumptions: dict[tuple[str, str, int], ValuationAssumption],
        cagr: RateAssumption,
        burn: bool,
    ) -> RateAssumption:
        override = drivers.get((GROWTH_KEY, year, scenario))
        if override and override["value"] is not None:
            origen = "del usuario" if override["user_override"] else "del modelo"
            return RateAssumption(
                override["value"],
                LABEL_INFERIDO,
                f"asuncion de driver '{GROWTH_KEY}' {origen} ({override['source']})",
            )
        stored = val_assumptions.get((GROWTH_KEY, scenario, year))
        if stored is not None:
            label = (
                LABEL_OFICIAL
                if (stored.source_type or "") in OFFICIAL_FACT_SOURCES
                else LABEL_INFERIDO
            )
            return RateAssumption(
                _num(stored.value),
                label,
                f"asuncion de valoracion persistida (tipo {stored.source_type})",
            )
        if cagr.value is None:
            return RateAssumption(None, LABEL_ND, None)
        if scenario == "base":
            return cagr
        if burn:
            # Con margen FCF negativo, mover el crecimiento invierte la
            # economia del escenario (crecer mas quema mas caja): la
            # dispersion honesta viene solo del margen, igual que en
            # mechanical_dcf_scenarios.
            return RateAssumption(
                cagr.value,
                LABEL_INFERIDO,
                f"{cagr.base}; sin dispersion por quema de caja (politica del modelo)",
            )
        delta = -GROWTH_SPREAD if scenario == "bear" else GROWTH_SPREAD
        return RateAssumption(
            cagr.value + delta,
            LABEL_INFERIDO,
            f"{cagr.base}; dispersion {delta:+.0%} sobre el base (politica del modelo)",
        )

    def _margin(
        self,
        scenario: str,
        year: int,
        *,
        drivers: dict[tuple[str, int, str], dict[str, Any]],
        val_assumptions: dict[tuple[str, str, int], ValuationAssumption],
        anchor: RateAssumption,
    ) -> RateAssumption:
        override = drivers.get((MARGIN_KEY, year, scenario))
        if override and override["value"] is not None:
            origen = "del usuario" if override["user_override"] else "del modelo"
            return RateAssumption(
                override["value"],
                LABEL_INFERIDO,
                f"asuncion de driver '{MARGIN_KEY}' {origen} ({override['source']})",
            )
        stored = val_assumptions.get((MARGIN_KEY, scenario, year))
        if stored is not None:
            label = (
                LABEL_OFICIAL
                if (stored.source_type or "") in OFFICIAL_FACT_SOURCES
                else LABEL_INFERIDO
            )
            return RateAssumption(
                _num(stored.value),
                label,
                f"asuncion de valoracion persistida (tipo {stored.source_type})",
            )
        if anchor.value is None:
            return RateAssumption(None, LABEL_ND, None)
        if scenario == "base":
            return anchor
        delta = -MARGIN_SPREAD if scenario == "bear" else MARGIN_SPREAD
        value = anchor.value + delta
        if scenario == "bull":
            value = min(value, MARGIN_CAP)
        return RateAssumption(
            value,
            LABEL_INFERIDO,
            f"{anchor.base}; dispersion {delta:+.0%} sobre el base (politica del modelo)",
        )

    def _margin_anchor(
        self,
        db: Session,
        company: Company,
        revenue: FactBase,
        fcf: FactBase,
    ) -> RateAssumption:
        """Margen FCF base: InferredInput validado o derivado de facts."""
        inferred = InferredInputService().latest_valid(db, company.id, MARGIN_KEY)
        if inferred is not None:
            return RateAssumption(
                _num(inferred.value),
                LABEL_INFERIDO,
                f"input inferido documentado: {inferred.base}",
                tuple(inferred.source_urls or ()),
            )
        if (
            revenue.value is not None
            and fcf.value is not None
            and revenue.value != 0
            and revenue.fiscal_year == fcf.fiscal_year
        ):
            return RateAssumption(
                fcf.value / revenue.value,
                LABEL_INFERIDO,
                f"margen FCF derivado de facts FY{revenue.fiscal_year} "
                f"(FCF / ingresos del mismo ejercicio)",
            )
        return RateAssumption(None, LABEL_ND, None)

    @staticmethod
    def _net_margin(revenue: FactBase, net_income: FactBase) -> RateAssumption:
        if (
            revenue.value is not None
            and net_income.value is not None
            and revenue.value != 0
            and revenue.fiscal_year == net_income.fiscal_year
        ):
            return RateAssumption(
                net_income.value / revenue.value,
                LABEL_INFERIDO,
                f"margen neto derivado de facts FY{revenue.fiscal_year} "
                f"(resultado neto / ingresos del mismo ejercicio)",
            )
        return RateAssumption(None, LABEL_ND, None)

    # -- precio objetivo ------------------------------------------------------

    def _current_price(
        self, db: Session, company: Company, as_of: date
    ) -> tuple[float | None, str | None]:
        price = _position_price(db, company.id)
        price_date = _position_price_as_of(db, company.id)
        if price_date:
            assert_no_lookahead(
                as_of=as_of,
                data_date=date.fromisoformat(price_date),
                label=f"precio {company.ticker}",
            )
        return price, price_date

    def _scenario_targets(
        self,
        db: Session,
        company: Company,
        as_of: date,
        anchor_kind: str | None,
        anchor_base_ps: float | None,
        projected_ps: dict[str, float | None],
        price: float | None,
    ) -> dict[str, dict[str, Any]]:
        """Precio objetivo a 5 anos por escenario.

        No reimplementa el DCF: toma el valor por accion actual de
        ValuationService y lo convierte en un multiplo implicito sobre el
        fundamental por accion (FCF si es positivo, si no ingresos), aplicado
        al fundamental proyectado del ultimo ejercicio. Si falta cualquier
        pieza, N/D.
        """
        valuation: dict[str, Any] | None = None
        valuation_error: str | None = None
        try:
            valuation = ValuationService().value_company(db, company, as_of=as_of)
        except Exception as exc:  # noqa: BLE001 - un motor roto no rompe la proyeccion
            valuation_error = type(exc).__name__
        out: dict[str, dict[str, Any]] = {}
        for scenario in SCENARIOS:
            target: float | None = None
            base: str | None = None
            if valuation_error is not None:
                base = f"valoracion no disponible ({valuation_error})"
            elif valuation is None or anchor_kind is None or anchor_base_ps in (None, 0):
                base = "sin ancla por accion (FCF o ingresos por accion no disponibles)"
            else:
                scenario_value = _num(valuation.get(f"{scenario}_value"))
                projected = projected_ps.get(scenario)
                if scenario_value is None or projected is None:
                    base = "sin valor del escenario o sin proyeccion del ancla"
                else:
                    multiple = scenario_value / anchor_base_ps
                    target = projected * multiple
                    base = (
                        f"multiplo implicito del modelo ({anchor_kind} por accion): "
                        f"valor/accion actual del escenario / {anchor_kind} por accion "
                        f"actual, aplicado al {anchor_kind} por accion proyectado"
                    )
            mos = margin_of_safety(target, price) if target is not None else None
            out[scenario] = {
                "valor": target,
                "etiqueta": LABEL_INFERIDO if target is not None else LABEL_ND,
                "base": base,
                "mos": mos,
            }
        return out

    # -- proyeccion -----------------------------------------------------------

    def project(
        self,
        db: Session,
        company: Company,
        *,
        as_of: date | None = None,
        horizon: int = HORIZON_YEARS,
    ) -> dict[str, Any]:
        as_of = as_of or date.today()
        horizon = max(1, min(int(horizon), 10))
        facts = self._annual_facts(db, company, as_of)
        revenue = self._fact_base(db, facts, "revenue")
        fcf = self._fact_base(db, facts, "free_cash_flow")
        net_income = self._fact_base(db, facts, "net_income")
        shares = self._fact_base(db, facts, "shares_diluted")

        drivers = self._driver_overrides(db, company)
        val_assumptions = self._valuation_assumptions(db, company)
        cagr = self._revenue_cagr(facts.get("revenue") or {})
        margin_anchor = self._margin_anchor(db, company, revenue, fcf)
        net_margin = self._net_margin(revenue, net_income)
        burn = margin_anchor.value is not None and margin_anchor.value < 0

        base_year = revenue.fiscal_year
        years = list(range(base_year + 1, base_year + horizon + 1)) if base_year else []

        price, price_date = self._current_price(db, company, as_of)

        scenarios: dict[str, dict[str, Any]] = {}
        for scenario in SCENARIOS:
            rows: list[dict[str, Any]] = []
            revenue_prev = revenue.value
            for year in years:
                growth = self._growth(
                    scenario,
                    year,
                    drivers=drivers,
                    val_assumptions=val_assumptions,
                    cagr=cagr,
                    burn=burn,
                )
                margin = self._margin(
                    scenario,
                    year,
                    drivers=drivers,
                    val_assumptions=val_assumptions,
                    anchor=margin_anchor,
                )
                if (
                    revenue_prev is not None
                    and growth.value is not None
                    and growth.value > -1
                ):
                    revenue_prev = revenue_prev * (1 + growth.value)
                    projected_revenue: float | None = revenue_prev
                else:
                    # Sin crecimiento valido la cadena se rompe: este ejercicio
                    # y los siguientes son N/D, nunca un arrastre del ultimo.
                    revenue_prev = None
                    projected_revenue = None
                projected_fcf = (
                    projected_revenue * margin.value
                    if projected_revenue is not None and margin.value is not None
                    else None
                )
                projected_eps = (
                    projected_revenue * net_margin.value / shares.value
                    if projected_revenue is not None
                    and net_margin.value is not None
                    and shares.value not in (None, 0)
                    else None
                )
                row_label = (
                    LABEL_INFERIDO
                    if projected_revenue is not None
                    else LABEL_ND
                )
                rows.append(
                    {
                        "ejercicio": year,
                        "ingresos": projected_revenue,
                        "fcf": projected_fcf,
                        "bps": projected_eps,
                        "etiqueta": row_label,
                        "etiquetas": {
                            "ingresos": LABEL_INFERIDO if projected_revenue is not None else LABEL_ND,
                            "fcf": LABEL_INFERIDO if projected_fcf is not None else LABEL_ND,
                            "bps": LABEL_INFERIDO if projected_eps is not None else LABEL_ND,
                        },
                        "crecimiento": growth.as_dict(),
                        "margen_fcf": margin.as_dict(),
                    }
                )
            scenarios[scenario] = {"proyecciones": rows}

        # Ancla por accion para el precio objetivo: FCF si es positivo, si no
        # ingresos, si no N/D. Con FCF negativo un multiplo de FCF no significa
        # nada; mejor N/D o el ancla de ingresos, declarada.
        anchor_kind: str | None = None
        anchor_base_ps: float | None = None
        if (
            fcf.value is not None
            and fcf.value > 0
            and shares.value not in (None, 0)
        ):
            anchor_kind = "fcf"
            anchor_base_ps = fcf.value / shares.value  # type: ignore[operator]
        elif (
            revenue.value is not None
            and revenue.value > 0
            and shares.value not in (None, 0)
        ):
            anchor_kind = "ingresos"
            anchor_base_ps = revenue.value / shares.value  # type: ignore[operator]

        projected_ps: dict[str, float | None] = {}
        for scenario in SCENARIOS:
            last = scenarios[scenario]["proyecciones"][-1] if years else None
            if last is None or anchor_kind is None or shares.value in (None, 0):
                projected_ps[scenario] = None
                continue
            anchor_value = last["fcf"] if anchor_kind == "fcf" else last["ingresos"]
            projected_ps[scenario] = (
                anchor_value / shares.value if anchor_value is not None else None
            )

        targets = self._scenario_targets(
            db, company, as_of, anchor_kind, anchor_base_ps, projected_ps, price
        )
        for scenario in SCENARIOS:
            scenarios[scenario]["precio_objetivo_5y"] = {
                **targets[scenario],
                "precio_actual": price,
                "precio_fecha": price_date,
            }

        aviso = self._coherence_warning(scenarios, years)

        return {
            "ticker": company.ticker,
            "model_type": MODEL_TYPE,
            "model_version": MODEL_VERSION,
            "generado_en": datetime.now(UTC).isoformat(),
            "as_of": as_of.isoformat(),
            "horizonte_anos": horizon,
            "ejercicio_base": base_year,
            "disclaimer": DISCLAIMER_ES,
            "base": {
                "ingresos": revenue.as_dict(),
                "fcf": fcf.as_dict(),
                "resultado_neto": net_income.as_dict(),
                "acciones": shares.as_dict(),
                "crecimiento_base": cagr.as_dict(),
                "margen_fcf_base": margin_anchor.as_dict(),
                "margen_neto_base": net_margin.as_dict(),
            },
            "ancla_precio_objetivo": anchor_kind,
            "escenarios": scenarios,
            "aviso_coherencia": aviso,
        }

    @staticmethod
    def _coherence_warning(
        scenarios: dict[str, dict[str, Any]], years: list[int]
    ) -> str | None:
        """bear <= base <= bull o aviso explicito; nunca se reordenan a escondidas."""
        problems: list[str] = []
        targets = [
            scenarios[s]["precio_objetivo_5y"]["valor"] for s in SCENARIOS
        ]
        if all(t is not None for t in targets) and not (
            targets[0] <= targets[1] <= targets[2]  # type: ignore[operator]
        ):
            problems.append("precio objetivo")
        if years:
            last_revenue = [
                scenarios[s]["proyecciones"][-1]["ingresos"] for s in SCENARIOS
            ]
            if all(v is not None for v in last_revenue) and not (
                last_revenue[0] <= last_revenue[1] <= last_revenue[2]  # type: ignore[operator]
            ):
                problems.append("ingresos proyectados")
        if not problems:
            return None
        return (
            f"los escenarios no quedan ordenados bear <= base <= bull en "
            f"{' y '.join(problems)}; se muestran los valores calculados, sin reordenar"
        )

    # -- persistencia y cuota --------------------------------------------------

    def persist(
        self,
        db: Session,
        company: Company,
        payload: dict[str, Any],
        *,
        commit: bool = True,
    ) -> ValuationModel:
        """Guarda el modelo (trace completo), salidas por escenario y filas anuales.

        Reutiliza ValuationModel/ValuationOutput con model_type='thesis_5y';
        las filas por ejercicio no caben en ValuationOutput (no tiene year ni
        revenue/fcf/eps) y van a thesis_projection_years. Un escenario con
        objetivo o MOS N/D NO genera ValuationOutput: grabar un 0 por defecto
        seria un valor inventado.
        """
        latest = db.scalar(
            select(ValuationModel)
            .where(ValuationModel.company_id == company.id)
            .order_by(desc(ValuationModel.version))
            .limit(1)
        )
        version = (latest.version + 1) if latest else 1
        has_target = any(
            payload["escenarios"][s]["precio_objetivo_5y"]["valor"] is not None
            for s in SCENARIOS
        )
        model = ValuationModel(
            company_id=company.id,
            model_type=MODEL_TYPE,
            version=version,
            status="final" if has_target else "draft",
            calculation_trace=payload,
        )
        db.add(model)
        db.flush()
        for scenario in SCENARIOS:
            target = payload["escenarios"][scenario]["precio_objetivo_5y"]
            if target["valor"] is None or target["mos"] is None:
                continue
            db.add(
                ValuationOutput(
                    valuation_model_id=model.id,
                    scenario=scenario,
                    value_per_share=Decimal(str(target["valor"])),
                    margin_of_safety=Decimal(str(target["mos"])),
                    output_payload=payload["escenarios"][scenario],
                )
            )
        day = datetime.now(UTC).date()
        tenant_id = db.info.get("tenant_id")
        # Idempotencia por dia: un recalculo sustituye las filas del dia, no
        # las apila (la UNIQUE tenant+company+scenario+year+day lo exige).
        db.execute(
            delete(ThesisProjectionYear).where(
                ThesisProjectionYear.company_id == company.id,
                ThesisProjectionYear.day == day,
                ThesisProjectionYear.tenant_id == tenant_id,
            )
        )
        for scenario in SCENARIOS:
            for row in payload["escenarios"][scenario]["proyecciones"]:
                growth_base = row["crecimiento"].get("base") or "N/D"
                db.add(
                    ThesisProjectionYear(
                        valuation_model_id=model.id,
                        company_id=company.id,
                        scenario=scenario,
                        fiscal_year=row["ejercicio"],
                        revenue=(
                            Decimal(str(row["ingresos"]))
                            if row["ingresos"] is not None
                            else None
                        ),
                        fcf=(
                            Decimal(str(row["fcf"]))
                            if row["fcf"] is not None
                            else None
                        ),
                        eps=(
                            Decimal(str(row["bps"]))
                            if row["bps"] is not None
                            else None
                        ),
                        label=row["etiqueta"],
                        source=f"crecimiento: {growth_base}"[:500],
                        as_of=date.fromisoformat(payload["as_of"]),
                        day=day,
                    )
                )
        if commit:
            db.commit()
            db.refresh(model)
        else:
            db.flush()
        return model

    def recalcs_today(self, db: Session, company: Company) -> int:
        """Recalculos persistidos hoy (UTC) por el tenant para esta empresa."""
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return db.scalar(
            select(func.count(ValuationModel.id)).where(
                ValuationModel.company_id == company.id,
                ValuationModel.model_type == MODEL_TYPE,
                ValuationModel.created_at >= start,
            )
        ) or 0

    def latest_persisted(self, db: Session, company: Company) -> dict[str, Any] | None:
        model = db.scalar(
            select(ValuationModel)
            .where(
                ValuationModel.company_id == company.id,
                ValuationModel.model_type == MODEL_TYPE,
            )
            .order_by(desc(ValuationModel.version))
            .limit(1)
        )
        if model is None:
            return None
        return {
            "valuation_model_id": model.id,
            "version": model.version,
            "status": model.status,
            "created_at": model.created_at.isoformat() if model.created_at else None,
        }
