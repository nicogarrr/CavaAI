from collections import defaultdict
from decimal import Decimal
from typing import Any


def _to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


def calculate_portfolio_risk(
    positions: list[dict],
    cash: list[dict],
    *,
    base_currency: str = "EUR",
    fx_rates: dict[str, float] | None = None,
) -> dict:
    """Aggregate portfolio risk with explicit FX conversion to ``base_currency``.

    ``fx_rates`` maps a currency code to its rate in ``base_currency`` (1 unit
    of that currency = rate units of base).  Currencies without a rate are
    **not** silently summed: they are reported in ``unconverted_currencies``
    and the result is ``status="unavailable"`` when any exposure is missing.
    """
    rates = {k.upper(): v for k, v in (fx_rates or {}).items()}
    base = base_currency.upper()
    rates.setdefault(base, 1.0)
    no_fx_provided = not fx_rates

    def convert(value: float, currency: str | None) -> float | None:
        cur = (currency or base).upper()
        if no_fx_provided:
            return value
        rate = rates.get(cur)
        if rate is None:
            return None
        return value * rate

    unconverted: list[str] = []
    equity_value = 0.0
    for position in positions:
        cur = position.get("currency") or base
        converted = convert(_to_float(position["market_value"]), cur)
        if converted is None:
            if cur.upper() not in unconverted:
                unconverted.append(cur.upper())
            continue
        equity_value += converted

    cash_by_currency: dict[str, float] = {}
    for item in cash:
        cur = (item.get("currency") or base).upper()
        balance = _to_float(item["balance"])
        converted = convert(balance, cur)
        if converted is None:
            if cur not in unconverted:
                unconverted.append(cur)
            continue
        cash_by_currency[cur] = cash_by_currency.get(cur, 0.0) + converted

    total_value = equity_value + sum(cash_by_currency.values())
    status = "unavailable" if unconverted else "ok"

    sector_exposure = defaultdict(float)
    factor_exposure = defaultdict(float)
    position_rows = []
    alerts = []

    for position in positions:
        cur = position.get("currency") or base
        converted = convert(_to_float(position["market_value"]), cur)
        if converted is None:
            continue
        weight = converted / total_value if total_value else 0
        sector_exposure[position["sector"]] += weight
        for tag in position.get("factor_tags", []):
            factor_exposure[tag] += weight
        position_rows.append({**position, "weight": weight})

        if weight > 0.20:
            alerts.append(
                {
                    "severity": "high",
                    "ticker": position["ticker"],
                    "message": f"{position['ticker']} exceeds 20% position weight",
                    "metric_value": weight,
                    "threshold": 0.20,
                }
            )
        if "pre_fcf" in position.get("factor_tags", []) and weight > 0.10:
            alerts.append(
                {
                    "severity": "medium",
                    "ticker": position["ticker"],
                    "message": f"{position['ticker']} is pre-FCF and above 10% weight",
                    "metric_value": weight,
                    "threshold": 0.10,
                }
            )

    for currency, balance in cash_by_currency.items():
        if balance < 0:
            alerts.append(
                {
                    "severity": "high",
                    "ticker": None,
                    "message": f"{currency} cash is negative",
                    "metric_value": balance,
                    "threshold": 0,
                }
            )

    sorted_positions = sorted(position_rows, key=lambda row: row["weight"], reverse=True)
    top_1 = sorted_positions[0]["weight"] if sorted_positions else 0
    top_5 = sum(row["weight"] for row in sorted_positions[:5])

    return {
        "status": status,
        "total_value": total_value if not unconverted else None,
        "equity_value": equity_value if not unconverted else None,
        "cash": cash_by_currency,
        "top_1_weight": top_1,
        "top_5_weight": top_5,
        "positions": sorted_positions,
        "sector_exposure": dict(sorted(sector_exposure.items())),
        "factor_exposure": dict(sorted(factor_exposure.items())),
        "alerts": alerts,
        "trace": {
            "base_currency": base,
            "fx_rates_used": dict(rates),
            "unconverted_currencies": unconverted,
        },
        "trace": {"method": "portfolio_risk_snapshot"},
    }

