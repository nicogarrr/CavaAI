from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BudgetUsage


class BudgetController:
    def __init__(self) -> None:
        self.settings = get_settings()

    def current_usage(self, db: Session) -> dict:
        today = date.today()
        daily = db.scalar(
            select(func.coalesce(func.sum(BudgetUsage.cost_eur), 0)).where(
                BudgetUsage.usage_date == today
            )
        )
        month_start = today.replace(day=1)
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
        monthly = db.scalar(
            select(func.coalesce(func.sum(BudgetUsage.cost_eur), 0)).where(
                BudgetUsage.usage_date >= month_start,
                BudgetUsage.usage_date < next_month,
            )
        )
        return {
            "daily_cost_eur": float(daily or 0),
            "monthly_cost_eur": float(monthly or 0),
            "daily_cap_eur": self.settings.llm_daily_cap_eur,
            "monthly_cap_eur": self.settings.llm_monthly_cap_eur,
        }

    def can_spend(self, db: Session, estimated_cost_eur: float) -> bool:
        usage = self.current_usage(db)
        return (
            usage["daily_cost_eur"] + estimated_cost_eur <= self.settings.llm_daily_cap_eur
            and usage["monthly_cost_eur"] + estimated_cost_eur <= self.settings.llm_monthly_cap_eur
        )

    def record(self, db: Session, model: str, workflow: str, cost_eur: float, tokens: int) -> None:
        db.add(
            BudgetUsage(
                usage_date=date.today(),
                model=model,
                workflow=workflow,
                cost_eur=Decimal(str(cost_eur)),
                token_count=tokens,
            )
        )
        db.commit()
