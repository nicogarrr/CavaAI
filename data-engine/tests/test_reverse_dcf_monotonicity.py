from app.valuation.reverse_dcf import ReverseDCFInputs, solve_required_growth


def test_reverse_dcf_withholds_growth_for_non_positive_margin():
    result = solve_required_growth(
        ReverseDCFInputs(
            market_price=10, revenue=1000, fcf_margin=-0.10, wacc=0.09,
            terminal_growth=0.02, net_debt=0, shares_outstanding=100,
        )
    )
    assert result["required_revenue_growth"] is None
    assert result["status"] == "not_applicable"
    assert result["out_of_bounds"] is True
