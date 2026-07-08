from dataclasses import dataclass


@dataclass(frozen=True)
class DilutionInput:
    current_shares: float
    new_capital_needed: float
    issuance_price: float
    current_value_per_share: float


def run_dilution(inputs: DilutionInput) -> dict:
    if inputs.current_shares <= 0:
        raise ValueError("current_shares must be positive")
    if inputs.issuance_price <= 0:
        raise ValueError("issuance_price must be positive")

    new_shares = max(inputs.new_capital_needed, 0) / inputs.issuance_price
    pro_forma_shares = inputs.current_shares + new_shares
    dilution_pct = new_shares / pro_forma_shares if pro_forma_shares else 0
    diluted_value_per_share = (
        inputs.current_value_per_share * inputs.current_shares
    ) / pro_forma_shares

    return {
        "new_shares": new_shares,
        "pro_forma_shares": pro_forma_shares,
        "dilution_pct": dilution_pct,
        "diluted_value_per_share": diluted_value_per_share,
        "trace": {"method": "simple_equity_dilution", "inputs": inputs.__dict__},
    }

