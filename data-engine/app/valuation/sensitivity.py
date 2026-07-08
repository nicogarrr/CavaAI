from collections.abc import Iterable

from app.valuation.dcf_fcff import DCFInputs, run_dcf


def sensitivity_grid(
    base: DCFInputs,
    growth_values: Iterable[float],
    wacc_values: Iterable[float],
) -> dict:
    rows = []
    for growth in growth_values:
        row = {"revenue_growth": growth, "values": []}
        for wacc in wacc_values:
            value = run_dcf(
                DCFInputs(
                    revenue=base.revenue,
                    revenue_growth=growth,
                    fcf_margin=base.fcf_margin,
                    wacc=wacc,
                    terminal_growth=base.terminal_growth,
                    net_debt=base.net_debt,
                    shares_outstanding=base.shares_outstanding,
                    years=base.years,
                )
            ).value_per_share
            row["values"].append({"wacc": wacc, "value_per_share": value})
        rows.append(row)
    return {"rows": rows, "trace": {"method": "dcf_sensitivity_grid"}}

