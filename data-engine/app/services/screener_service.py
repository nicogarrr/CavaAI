"""Safe custom metrics and persistent, evidence-aware company screens."""

from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    CalculatedMetric,
    Company,
    CustomMetricDefinition,
    FinancialFact,
    SavedScreen,
    SavedScreenMatch,
)
from app.services.review_alert_service import ReviewAlertService


KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,159}$")
COMPARATORS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


class MissingVariables(ValueError):
    def __init__(self, names: set[str]) -> None:
        self.names = names
        super().__init__(f"Missing variables: {', '.join(sorted(names))}")


class SafeFormula:
    FUNCTIONS = {"min": min, "max": max, "abs": abs}
    BINARY = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.Mod: operator.mod,
    }
    UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}

    def __init__(self, expression: str) -> None:
        if len(expression) > 1000:
            raise ValueError("Formula exceeds 1000 characters")
        try:
            self.tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError("Invalid formula syntax") from exc
        self.expression = expression
        self.names: set[str] = set()
        self._validate(self.tree)

    def _validate(self, node: ast.AST) -> None:
        if isinstance(node, ast.Expression):
            self._validate(node.body)
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
                raise ValueError("Only numeric constants are allowed")
        elif isinstance(node, ast.Name):
            if not KEY_RE.fullmatch(node.id):
                raise ValueError(f"Invalid metric name: {node.id}")
            self.names.add(node.id)
        elif isinstance(node, ast.BinOp):
            if type(node.op) not in self.BINARY:
                raise ValueError("Formula operator is not allowed")
            self._validate(node.left)
            self._validate(node.right)
        elif isinstance(node, ast.UnaryOp):
            if type(node.op) not in self.UNARY:
                raise ValueError("Formula unary operator is not allowed")
            self._validate(node.operand)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in self.FUNCTIONS:
                raise ValueError("Only min, max and abs functions are allowed")
            if node.keywords:
                raise ValueError("Formula keyword arguments are not allowed")
            for argument in node.args:
                self._validate(argument)
        else:
            raise ValueError(f"Formula element {type(node).__name__} is not allowed")

    def evaluate(self, values: dict[str, Decimal]) -> Decimal:
        missing = self.names - values.keys()
        if missing:
            raise MissingVariables(missing)
        try:
            result = self._evaluate(self.tree.body, values)
            if not result.is_finite():
                raise ValueError("Formula result is not finite")
            return result
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise ValueError("Formula cannot be evaluated for these values") from exc

    def _evaluate(self, node: ast.AST, values: dict[str, Decimal]) -> Decimal:
        if isinstance(node, ast.Constant):
            return Decimal(str(node.value))
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.BinOp):
            left = self._evaluate(node.left, values)
            right = self._evaluate(node.right, values)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("Formula exponent exceeds safe limit")
            return self.BINARY[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp):
            return self.UNARY[type(node.op)](self._evaluate(node.operand, values))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            arguments = [self._evaluate(argument, values) for argument in node.args]
            return self.FUNCTIONS[node.func.id](*arguments)
        raise ValueError("Invalid formula node")


@dataclass
class Observation:
    value: Decimal
    confidence: Decimal
    as_of: date | datetime | None
    period: str
    source: str
    source_ids: list[int]


class CustomMetricService:
    def create(
        self,
        db: Session,
        *,
        metric_key: str,
        name: str,
        formula: str,
        unit: str,
        description: str,
    ) -> CustomMetricDefinition:
        metric_key = metric_key.strip().lower()
        if not KEY_RE.fullmatch(metric_key):
            raise ValueError("metric_key must be lower-case snake_case")
        parsed = SafeFormula(formula)
        if metric_key in parsed.names:
            raise ValueError("Custom metric cannot reference itself")
        previous = db.scalar(
            select(CustomMetricDefinition)
            .where(CustomMetricDefinition.metric_key == metric_key)
            .order_by(desc(CustomMetricDefinition.version))
            .limit(1)
        )
        if previous:
            previous.active = False
        definition = CustomMetricDefinition(
            metric_key=metric_key,
            name=name.strip(),
            formula=formula.strip(),
            unit=unit.strip() or "decimal",
            description=description.strip(),
            version=previous.version + 1 if previous else 1,
            active=True,
            metadata_={"dependencies": sorted(parsed.names), "engine": "safe_ast_v1"},
        )
        db.add(definition)
        db.commit()
        db.refresh(definition)
        return definition

    @staticmethod
    def active(db: Session) -> list[CustomMetricDefinition]:
        return list(
            db.scalars(
                select(CustomMetricDefinition)
                .where(CustomMetricDefinition.active.is_(True))
                .order_by(CustomMetricDefinition.metric_key)
            ).all()
        )


class ScreenerService:
    def create_screen(
        self,
        db: Session,
        *,
        name: str,
        description: str,
        criteria: list[dict[str, Any]],
        ranking_formula: str | None,
        ranking_direction: str,
        alerts_enabled: bool,
    ) -> SavedScreen:
        if not criteria:
            raise ValueError("A screen requires at least one criterion")
        normalized = [self._criterion(item) for item in criteria]
        if ranking_formula:
            SafeFormula(ranking_formula)
        if ranking_direction not in {"asc", "desc"}:
            raise ValueError("ranking_direction must be asc or desc")
        screen = SavedScreen(
            name=name.strip(),
            description=description.strip(),
            criteria=normalized,
            ranking_formula=ranking_formula.strip() if ranking_formula else None,
            ranking_direction=ranking_direction,
            alerts_enabled=alerts_enabled,
            active=True,
            metadata_={"criteria_version": 1, "formula_engine": "safe_ast_v1"},
        )
        db.add(screen)
        db.commit()
        db.refresh(screen)
        return screen

    def run_saved(self, db: Session, screen: SavedScreen) -> dict[str, Any]:
        response = self.run(
            db,
            criteria=screen.criteria,
            ranking_formula=screen.ranking_formula,
            ranking_direction=screen.ranking_direction,
        )
        now = datetime.now(UTC)
        matched_ids = {row["company_id"] for row in response["results"] if row["matched"]}
        existing = {
            row.company_id: row
            for row in db.scalars(
                select(SavedScreenMatch).where(SavedScreenMatch.saved_screen_id == screen.id)
            ).all()
        }
        new_company_ids: list[int] = []
        by_company = {row["company_id"]: row for row in response["results"]}
        for company_id in matched_ids:
            match = existing.get(company_id)
            is_new = match is None or not match.active
            if match is None:
                match = SavedScreenMatch(
                    saved_screen_id=screen.id,
                    company_id=company_id,
                    first_matched_at=now,
                    last_matched_at=now,
                )
                db.add(match)
            match.active = True
            match.last_matched_at = now
            match.result = by_company[company_id]
            if is_new:
                new_company_ids.append(company_id)
                if screen.alerts_enabled:
                    company = db.get(Company, company_id)
                    ReviewAlertService().emit_alert(
                        db,
                        company_id=company_id,
                        alert_type="new_screen_match",
                        severity="medium",
                        title=f"New match: {screen.name}",
                        message=f"{company.ticker if company else company_id} now matches {screen.name}",
                        fingerprint_parts=["saved_screen", str(screen.id), str(company_id)],
                        metadata={
                            "saved_screen_id": screen.id,
                            "result": by_company[company_id],
                        },
                    )
        for company_id, match in existing.items():
            if match.active and company_id not in matched_ids:
                match.active = False
        screen.last_run_at = now
        db.commit()
        response["saved_screen_id"] = screen.id
        response["new_match_company_ids"] = new_company_ids
        return response

    def run(
        self,
        db: Session,
        *,
        criteria: list[dict[str, Any]],
        ranking_formula: str | None = None,
        ranking_direction: str = "desc",
    ) -> dict[str, Any]:
        normalized = [self._criterion(item) for item in criteria]
        ranking = SafeFormula(ranking_formula) if ranking_formula else None
        definitions = CustomMetricService.active(db)
        results = []
        for company in db.scalars(select(Company).order_by(Company.ticker)).all():
            observations = self._observations(db, company)
            self._custom_metrics(observations, definitions)
            values = {key: item.value for key, item in observations.items()}
            criterion_results = []
            missing: set[str] = set()
            used_names: set[str] = set()
            if ranking:
                used_names.update(ranking.names)
            for criterion in normalized:
                left = SafeFormula(criterion["left"])
                right = SafeFormula(criterion["right"])
                used_names.update(left.names | right.names)
                try:
                    left_value = left.evaluate(values)
                    right_value = right.evaluate(values)
                    passed = COMPARATORS[criterion["operator"]](left_value, right_value)
                    criterion_results.append(
                        {
                            **criterion,
                            "left_value": str(left_value),
                            "right_value": str(right_value),
                            "passed": passed,
                        }
                    )
                except MissingVariables as exc:
                    expanded = self._expand_missing(exc.names, definitions, values)
                    missing.update(expanded)
                    criterion_results.append(
                        {**criterion, "passed": False, "missing_fields": sorted(expanded)}
                    )
            rank_value = None
            if ranking:
                try:
                    rank_value = ranking.evaluate(values)
                except MissingVariables as exc:
                    missing.update(self._expand_missing(exc.names, definitions, values))
            available = {name for name in used_names - missing if name in observations}
            confidence_values = [observations[name].confidence for name in available]
            dates = [observations[name].as_of for name in available if observations[name].as_of]
            results.append(
                {
                    "company_id": company.id,
                    "ticker": company.ticker,
                    "name": company.name,
                    "matched": not missing and all(item["passed"] for item in criterion_results),
                    "rank_value": str(rank_value) if rank_value is not None else None,
                    "coverage_percent": round(100 * len(available) / len(used_names), 1)
                    if used_names
                    else 100.0,
                    "confidence": str(sum(confidence_values, Decimal("0")) / len(confidence_values))
                    if confidence_values
                    else "0",
                    "latest_data_at": max(dates).isoformat() if dates else None,
                    "missing_fields": sorted(missing),
                    "criteria": criterion_results,
                }
            )

        def result_order(row: dict[str, Any]) -> tuple[Any, ...]:
            missing_rank = row["rank_value"] is None
            rank_value = Decimal(row["rank_value"]) if row["rank_value"] is not None else Decimal("0")
            ordered_rank = rank_value if ranking_direction == "asc" else -rank_value
            return (not row["matched"], missing_rank, ordered_rank, row["ticker"])

        results.sort(key=result_order)
        return {
            "criteria": normalized,
            "ranking_formula": ranking_formula,
            "ranking_direction": ranking_direction,
            "company_count": len(results),
            "match_count": sum(1 for row in results if row["matched"]),
            "results": results,
        }

    @staticmethod
    def _expand_missing(
        names: set[str],
        definitions: list[CustomMetricDefinition],
        values: dict[str, Decimal],
    ) -> set[str]:
        by_key = {definition.metric_key: definition for definition in definitions}
        expanded = set(names)
        pending = list(names)
        while pending:
            name = pending.pop()
            definition = by_key.get(name)
            if definition is None:
                continue
            for dependency in SafeFormula(definition.formula).names:
                if dependency not in values and dependency not in expanded:
                    expanded.add(dependency)
                    pending.append(dependency)
        return expanded

    @staticmethod
    def _criterion(item: dict[str, Any]) -> dict[str, str]:
        left = str(item.get("left") or item.get("metric") or "").strip()
        operator_key = str(item.get("operator") or "").strip()
        raw_right = item.get("right", item.get("value"))
        right = str(raw_right).strip()
        if not left or not right or operator_key not in COMPARATORS:
            raise ValueError("Each criterion needs left, operator and right")
        SafeFormula(left)
        SafeFormula(right)
        return {"left": left, "operator": operator_key, "right": right}

    def _observations(self, db: Session, company: Company) -> dict[str, Observation]:
        result: dict[str, Observation] = {}
        calculated = db.scalars(
            select(CalculatedMetric)
            .where(
                CalculatedMetric.company_id == company.id,
                CalculatedMetric.value.is_not(None),
                CalculatedMetric.status == "ok",
            )
            .order_by(CalculatedMetric.metric, desc(CalculatedMetric.fiscal_year), desc(CalculatedMetric.id))
        ).all()
        for metric in calculated:
            if metric.metric not in result and metric.value is not None:
                result[metric.metric] = Observation(
                    metric.value,
                    metric.confidence,
                    metric.updated_at,
                    metric.period,
                    "calculated_metric",
                    [metric.id],
                )
        facts = list(
            db.scalars(
                select(FinancialFact)
                .where(FinancialFact.company_id == company.id)
                .order_by(FinancialFact.metric, desc(FinancialFact.fiscal_year), desc(FinancialFact.id))
            ).all()
        )
        by_metric: dict[str, list[FinancialFact]] = {}
        for fact in facts:
            by_metric.setdefault(fact.metric, []).append(fact)
            result.setdefault(
                fact.metric,
                Observation(
                    fact.value,
                    fact.confidence,
                    fact.updated_at,
                    fact.period,
                    fact.source_type,
                    [fact.id],
                ),
            )
        for key, series in by_metric.items():
            cagr = self._cagr(series)
            if cagr:
                result[f"{key}_cagr"] = cagr
        if "shares_diluted_cagr" in result:
            result["shares_cagr"] = result["shares_diluted_cagr"]
        fcf_per_share = self._ratio_cagr(
            by_metric.get("free_cash_flow", []),
            by_metric.get("shares_diluted", []),
        )
        if fcf_per_share:
            result["fcf_per_share_cagr"] = fcf_per_share
        return result

    @staticmethod
    def _cagr(series: list[FinancialFact]) -> Observation | None:
        annual = {
            fact.fiscal_year: fact
            for fact in series
            if fact.fiscal_year is not None and not (fact.fiscal_quarter or "").upper().startswith("Q")
        }
        years = sorted(annual)
        if len(years) < 2:
            return None
        first, last = annual[years[0]], annual[years[-1]]
        if first.value <= 0 or last.value < 0:
            return None
        value = (last.value / first.value) ** (Decimal("1") / (years[-1] - years[0])) - 1
        return Observation(
            value,
            min(first.confidence, last.confidence),
            last.updated_at,
            f"FY{years[0]}-FY{years[-1]}",
            "calculated_cagr",
            [first.id, last.id],
        )

    def _ratio_cagr(
        self, numerators: list[FinancialFact], denominators: list[FinancialFact]
    ) -> Observation | None:
        numerator_by_year = {row.fiscal_year: row for row in numerators if row.fiscal_year}
        denominator_by_year = {row.fiscal_year: row for row in denominators if row.fiscal_year}
        years = sorted(numerator_by_year.keys() & denominator_by_year.keys())
        if len(years) < 2:
            return None
        first_year, last_year = years[0], years[-1]
        first_n, last_n = numerator_by_year[first_year], numerator_by_year[last_year]
        first_d, last_d = denominator_by_year[first_year], denominator_by_year[last_year]
        if first_d.value == 0 or last_d.value == 0:
            return None
        synthetic = [
            FinancialFact(
                id=first_n.id,
                company_id=first_n.company_id,
                metric="fcf_per_share",
                value=first_n.value / first_d.value,
                period=f"FY{first_year}",
                fiscal_year=first_year,
                confidence=min(first_n.confidence, first_d.confidence),
            ),
            FinancialFact(
                id=last_n.id,
                company_id=last_n.company_id,
                metric="fcf_per_share",
                value=last_n.value / last_d.value,
                period=f"FY{last_year}",
                fiscal_year=last_year,
                confidence=min(last_n.confidence, last_d.confidence),
            ),
        ]
        observation = self._cagr(synthetic)
        if observation:
            observation.source_ids = [first_n.id, first_d.id, last_n.id, last_d.id]
            observation.as_of = last_n.updated_at
        return observation

    @staticmethod
    def _custom_metrics(
        observations: dict[str, Observation],
        definitions: list[CustomMetricDefinition],
    ) -> None:
        pending = list(definitions)
        for _ in range(len(pending) + 1):
            changed = False
            values = {key: item.value for key, item in observations.items()}
            for definition in list(pending):
                formula = SafeFormula(definition.formula)
                try:
                    value = formula.evaluate(values)
                except MissingVariables:
                    continue
                dependencies = [observations[name] for name in formula.names]
                observations[definition.metric_key] = Observation(
                    value=value,
                    confidence=min(
                        (item.confidence for item in dependencies),
                        default=Decimal("0"),
                    ),
                    as_of=max(
                        (item.as_of for item in dependencies if item.as_of),
                        default=None,
                    ),
                    period=max((item.period for item in dependencies), default="unknown"),
                    source=f"custom_metric_v{definition.version}",
                    source_ids=[source_id for item in dependencies for source_id in item.source_ids],
                )
                pending.remove(definition)
                changed = True
            if not changed:
                break
