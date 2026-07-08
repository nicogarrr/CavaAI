def run_sotp(segments: list[dict], net_debt: float, shares_outstanding: float) -> dict:
    if shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be positive")

    segment_values = []
    for segment in segments:
        metric = float(segment["metric"])
        multiple = float(segment["multiple"])
        value = metric * multiple
        segment_values.append({**segment, "value": value})

    enterprise_value = sum(segment["value"] for segment in segment_values)
    equity_value = enterprise_value - net_debt
    return {
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "value_per_share": equity_value / shares_outstanding,
        "segments": segment_values,
        "trace": {"method": "sum_of_the_parts"},
    }

