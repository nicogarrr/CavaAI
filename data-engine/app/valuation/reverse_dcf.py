from dataclasses import dataclass

from app.valuation.dcf_fcff import DCFInputs, run_dcf


@dataclass(frozen=True)
class ReverseDCFInputs:
    market_price: float
    revenue: float
    fcf_margin: float
    wacc: float
    terminal_growth: float
    net_debt: float
    shares_outstanding: float
    low_growth: float = -0.25
    high_growth: float = 0.75
    years: int = 5


def solve_required_growth(inputs: ReverseDCFInputs, iterations: int = 60) -> dict:
    low = inputs.low_growth
    high = inputs.high_growth

    for _ in range(iterations):
        mid = (low + high) / 2
        value = run_dcf(
            DCFInputs(
                revenue=inputs.revenue,
                revenue_growth=mid,
                fcf_margin=inputs.fcf_margin,
                wacc=inputs.wacc,
                terminal_growth=inputs.terminal_growth,
                net_debt=inputs.net_debt,
                shares_outstanding=inputs.shares_outstanding,
                years=inputs.years,
            )
        ).value_per_share

        if value < inputs.market_price:
            low = mid
        else:
            high = mid

    required_growth = (low + high) / 2
    result_value = run_dcf(
        DCFInputs(
            revenue=inputs.revenue,
            revenue_growth=required_growth,
            fcf_margin=inputs.fcf_margin,
            wacc=inputs.wacc,
            terminal_growth=inputs.terminal_growth,
            net_debt=inputs.net_debt,
            shares_outstanding=inputs.shares_outstanding,
            years=inputs.years,
        )
    ).value_per_share

    return {
        "required_revenue_growth": required_growth,
        "market_price": inputs.market_price,
        "solved_value_per_share": result_value,
        "trace": {
            "method": "binary_search_reverse_dcf",
            "iterations": iterations,
            "growth_bounds": [inputs.low_growth, inputs.high_growth],
        },
    }

