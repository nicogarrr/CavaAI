from dataclasses import dataclass


@dataclass(frozen=True)
class DilutionInput:
    current_shares: float
    new_capital_needed: float
    issuance_price: float
    current_value_per_share: float


def run_dilution(inputs: DilutionInput) -> dict:
    """Dilution pro-forma, con credito por el capital captado.

    Una emision a valor de mercado es neutra: si se captan C dolares a un
    precio igual al valor por accion, el equity pasa a (E + C) y las acciones
    a (S + C/P), de modo que el valor por accion no cambia. Repartir el equity
    *pre-emision* sobre las acciones pro-forma (la version anterior) trata el
    capital captado como si tuviera valor cero, que es equivalente a emitir
    siempre con descuento y destruye valor en cualquier caso.
    """
    if inputs.current_shares <= 0:
        raise ValueError("current_shares must be positive")
    if inputs.issuance_price <= 0:
        raise ValueError("issuance_price must be positive")

    capital_raised = max(inputs.new_capital_needed, 0.0)
    new_shares = capital_raised / inputs.issuance_price
    pro_forma_shares = inputs.current_shares + new_shares
    dilution_pct = new_shares / pro_forma_shares if pro_forma_shares else 0

    pre_equity = inputs.current_value_per_share * inputs.current_shares
    post_equity = pre_equity + capital_raised
    diluted_value_per_share = post_equity / pro_forma_shares

    # Sin credito por la emission (comportamiento anterior, expuesto para
    # poder auditar cuanto valor destruia el supuesto).
    value_erosion_per_share = (
        pre_equity / pro_forma_shares if pro_forma_shares else None
    )
    # >1 = emision por encima del valor (acretiva), <1 = por debajo (dilutiva).
    issuance_premium = inputs.issuance_price / inputs.current_value_per_share if inputs.current_value_per_share else None

    return {
        "new_shares": new_shares,
        "pro_forma_shares": pro_forma_shares,
        "dilution_pct": dilution_pct,
        "diluted_value_per_share": diluted_value_per_share,
        "capital_raised": capital_raised,
        "pre_equity_value": pre_equity,
        "post_equity_value": post_equity,
        "issuance_premium_to_value": issuance_premium,
        "value_per_share_without_issuance_credit": value_erosion_per_share,
        "trace": {
            "method": "pro_forma_equity_with_issuance_credit",
            "inputs": dict(inputs.__dict__),
            "note": (
                "value_per_share = (pre_equity + capital_raised) / pro_forma_shares. "
                "A market-price issuance is value-neutral; a discount dilutes."
            ),
        },
    }

