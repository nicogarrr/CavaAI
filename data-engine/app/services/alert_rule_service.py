from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    AlertRule,
    Company,
    EarningsRun,
    FinancialFact,
    MarketPrice,
    NewsEvent,
    Position,
)
from app.services.review_alert_service import ReviewAlertService


class AlertRuleService:
    def create(
        self,
        db: Session,
        company: Company,
        *,
        rule_type: str,
        operator: str,
        value: float | str,
        cooldown_seconds: int = 3600,
    ) -> AlertRule:
        if rule_type in {"news", "earnings"}:
            operator, value = ">", 0
        name = f"{company.ticker}: {rule_type} {operator} {value}"[:300]
        target = self._target(rule_type)
        rule = db.scalar(
            select(AlertRule).where(
                AlertRule.company_id == company.id,
                AlertRule.name == name,
            )
        )
        if rule is None:
            rule = AlertRule(company_id=company.id, name=name)
            db.add(rule)
        rule.rule_type = rule_type
        rule.condition = {"operator": operator, "value": value}
        rule.target = target
        rule.severity = "medium"
        rule.channels = ["in_app"]
        rule.active = True
        rule.cooldown_seconds = max(0, cooldown_seconds)
        rule.metadata_ = {"ticker": company.ticker, "source": "user"}
        db.commit()
        db.refresh(rule)
        return rule

    def evaluate_all(self, db: Session) -> list[dict[str, Any]]:
        rules = list(
            db.scalars(
                select(AlertRule)
                .where(AlertRule.active.is_(True))
                .order_by(AlertRule.id)
            ).all()
        )
        results = [self.evaluate(db, rule, commit=False) for rule in rules]
        db.commit()
        return results

    def evaluate(
        self, db: Session, rule: AlertRule, *, commit: bool = True
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        company = db.get(Company, rule.company_id)
        if company is None:
            rule.active = False
            result = {"rule_id": rule.id, "status": "disabled_missing_company"}
            rule.last_result = result
            if commit:
                db.commit()
            return result

        observed, observation = self._observe(db, rule)
        matched = self._matches(
            observed,
            str((rule.condition or {}).get("operator") or "=="),
            (rule.condition or {}).get("value"),
        )
        cooldown_until = (
            self._aware(rule.last_triggered_at)
            + timedelta(seconds=rule.cooldown_seconds)
            if rule.last_triggered_at
            else None
        )
        cooldown_active = bool(cooldown_until and cooldown_until > now)
        triggered = bool(matched and not cooldown_active)
        if triggered:
            ReviewAlertService().emit_alert(
                db,
                company_id=company.id,
                alert_type=rule.rule_type,
                severity=rule.severity,
                title=rule.name,
                message=(
                    f"{company.ticker} rule matched: observed={observed}; "
                    f"condition={rule.condition}"
                ),
                fingerprint_parts=["alert_rule", str(rule.id)],
                channels=rule.channels,
                metadata={
                    "alert_rule_id": rule.id,
                    "condition": rule.condition,
                    "target": rule.target,
                    "observation": observation,
                },
            )
            rule.last_triggered_at = now
            rule.trigger_count += 1
        result = {
            "rule_id": rule.id,
            "status": "triggered" if triggered else "evaluated",
            "matched": bool(matched),
            "cooldown_active": cooldown_active,
            "observed": self._json_value(observed),
            "observation": observation,
        }
        rule.last_evaluated_at = now
        rule.last_value = None if observed is None else str(observed)[:160]
        rule.last_result = result
        if commit:
            db.commit()
            db.refresh(rule)
        return result

    def _observe(self, db: Session, rule: AlertRule) -> tuple[Any, dict[str, Any]]:
        kind = str((rule.target or {}).get("kind") or "")
        if kind == "market_price":
            prices = list(
                db.scalars(
                    select(MarketPrice)
                    .where(MarketPrice.company_id == rule.company_id)
                    .order_by(desc(MarketPrice.date))
                    .limit(2)
                ).all()
            )
            if prices:
                return Decimal(prices[0].close), {
                    "kind": kind,
                    "market_price_id": prices[0].id,
                    "date": prices[0].date.isoformat(),
                }
            position = db.scalar(
                select(Position)
                .where(Position.company_id == rule.company_id)
                .order_by(desc(Position.as_of))
                .limit(1)
            )
            return (
                (Decimal(position.market_price), {"kind": kind, "position_id": position.id})
                if position and position.market_price is not None
                else (None, {"kind": kind, "status": "missing"})
            )
        if kind == "price_change_percent":
            prices = list(
                db.scalars(
                    select(MarketPrice)
                    .where(MarketPrice.company_id == rule.company_id)
                    .order_by(desc(MarketPrice.date))
                    .limit(2)
                ).all()
            )
            if len(prices) < 2 or prices[1].close == 0:
                return None, {"kind": kind, "status": "missing_two_prices"}
            change = (Decimal(prices[0].close) / Decimal(prices[1].close) - 1) * 100
            return change, {"kind": kind, "price_ids": [prices[0].id, prices[1].id]}
        since = self._aware(rule.last_evaluated_at) or self._aware(rule.created_at)
        if kind == "news_event":
            statement = (
                select(NewsEvent)
                .where(NewsEvent.company_id == rule.company_id)
                .order_by(desc(NewsEvent.created_at))
                .limit(1)
            )
            if since:
                statement = statement.where(NewsEvent.created_at > since)
            event = db.scalar(statement)
            return (1 if event else 0), {
                "kind": kind,
                "news_event_id": event.id if event else None,
            }
        if kind == "earnings_run":
            statement = (
                select(EarningsRun)
                .where(EarningsRun.company_id == rule.company_id)
                .order_by(desc(EarningsRun.created_at))
                .limit(1)
            )
            if since:
                statement = statement.where(EarningsRun.created_at > since)
            run = db.scalar(statement)
            return (1 if run else 0), {
                "kind": kind,
                "earnings_run_id": run.id if run else None,
            }
        if kind == "financial_metric":
            metric = str((rule.target or {}).get("metric") or "")
            fact = db.scalar(
                select(FinancialFact)
                .where(
                    FinancialFact.company_id == rule.company_id,
                    FinancialFact.metric == metric,
                )
                .order_by(desc(FinancialFact.fiscal_year), desc(FinancialFact.created_at))
                .limit(1)
            )
            return (
                (Decimal(fact.value), {"kind": kind, "financial_fact_id": fact.id})
                if fact
                else (None, {"kind": kind, "status": "missing"})
            )
        return None, {"kind": kind, "status": "unsupported_target"}

    @staticmethod
    def _matches(observed: Any, operator: str, expected: Any) -> bool:
        if observed is None:
            return False
        try:
            left = Decimal(str(observed))
            right = Decimal(str(expected))
        except (InvalidOperation, TypeError, ValueError):
            left, right = str(observed), str(expected)
        operations = {
            ">": lambda: left > right,
            "<": lambda: left < right,
            ">=": lambda: left >= right,
            "<=": lambda: left <= right,
            "==": lambda: left == right,
        }
        return bool(operations.get(operator, lambda: False)())

    @staticmethod
    def _target(rule_type: str) -> dict[str, Any]:
        return {
            "price_above": {"kind": "market_price"},
            "price_below": {"kind": "market_price"},
            "price_change": {"kind": "price_change_percent"},
            "news": {"kind": "news_event"},
            "earnings": {"kind": "earnings_run"},
        }[rule_type]

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value
