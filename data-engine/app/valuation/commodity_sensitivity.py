def commodity_price_sensitivity(
    base_volume: float,
    cash_cost_per_unit: float,
    commodity_prices: list[float],
    tax_rate: float,
    multiple: float,
    net_debt: float,
    shares_outstanding: float,
) -> dict:
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")

    rows = []
    for price in commodity_prices:
        ebitda = max(price - cash_cost_per_unit, 0) * base_volume
        after_tax = ebitda * (1 - tax_rate)
        equity_value = after_tax * multiple - net_debt
        rows.append(
            {
                "commodity_price": price,
                "after_tax_cash_flow": after_tax,
                "equity_value": equity_value,
                "value_per_share": equity_value / shares_outstanding,
            }
        )

    return {"rows": rows, "trace": {"method": "commodity_price_sensitivity"}}

