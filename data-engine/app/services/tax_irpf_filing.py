"""Capa de declaración IRPF (Modelo 100) sobre el informe fiscal existente.

Convierte los agregados del :class:`TaxReportService` (dividendos, ventas
FIFO, retenciones) en las casillas del Modelo 100 y en la deducción por
doble imposición internacional (art. 80 LIRPF).

Referencia de enfoque: DeclaRenta (GPL-3.0, github.com/GeiserX/DeclaRenta).
El diseño de casillas se ha verificado contra el anexo del Modelo 100 en la
propia Orden HAC/277/2026 (BOE-A-2026-7041): 0326/0327 emisora-denominación,
0328 importe global de transmisiones, 0331 adquisición global, 0336/0338
resultados por fila, 0339/0340 sumas; 0029 dividendos; 0588 doble imposición
internacional; 0597 retenciones por rendimientos del capital mobiliario;
1626/1633/1637/1640 y 0385/0386 otros elementos patrimoniales.
Aquí se reimplementa en Python el MAPEO NORMATIVO (números de casilla de la
Orden HAC/277/2026 para la Renta 2025, escala del ahorro, límites del
art. 80 LIRPF); no se copia código fuente. Los números de casilla son
hechos normativos publicados en el BOE.

Alcance deliberado (honesto, sin verde falso):
- El mapeo de casillas verificado es el de la Renta 2025 (Orden HAC/277/2026,
  BOE-A-2026-7041). Para otros ejercicios el bloque ``casillas`` se devuelve
  con ``available=False`` y el motivo, no con números de otro año.
- Todas las ventas del ledger son acciones/ETF cotizados (el importador IBKR
  solo crea operaciones de acciones), así que todo va al bloque de "acciones
  negociadas" (pág. 14 III, art. 37.1.a LIRPF). Opciones/cripto no entran en
  CavaAI; si algún día se importan, hay que enrutarlas a "otros elementos"
  (pág. 17 I, casillas 1626/1633/1637/1640) antes de usar esto.
- El país de retención se aproxima con ``Company.domicile_country`` (el
  ledger no guarda país de retención por pago). Si falta, el país es
  "desconocido": NO se calcula deducción para ese bloque y se marca para
  revisión manual. Con ISIN (pendiente) se podrá afinar por prefijo.
- Dividendos especiales (REIT, retorno de capital, payment in lieu) y
  préstamo de acciones NO se clasifican: se listan como ``manual_review``
  cuando el tipo de pago no es dividendo ordinario + retención.
- Sigue siendo un informe ORIENTATIVO (ver ``summary.fiscal_disclaimer``):
  una ayuda de cálculo para contrastar con los extractos oficiales, no una
  declaración lista para presentar.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# --- Escala del ahorro (base del ahorro) -----------------------------------
# Historial del tipo del ahorro:
#  - 2021-2022: 19 / 21 / 23 / 26 (tramo superior > 200.000)
#  - 2023-2024: 19 / 21 / 23 / 27 / 28 (RDL 13/2022: 27% entre 200k-300k, 28% >300k)
#  - 2025+:     19 / 21 / 23 / 27 / 30 (Ley 7/2024 sube el tramo >300.000 al 30%)
# Cada banda es (desde, hasta, tipo); el tramo superior usa hasta=None.

_BRACKETS_2021 = ((0, 6_000, Decimal("0.19")), (6_000, 50_000, Decimal("0.21")),
                  (50_000, 200_000, Decimal("0.23")), (200_000, None, Decimal("0.26")))
_BRACKETS_2023 = ((0, 6_000, Decimal("0.19")), (6_000, 50_000, Decimal("0.21")),
                  (50_000, 200_000, Decimal("0.23")), (200_000, 300_000, Decimal("0.27")),
                  (300_000, None, Decimal("0.28")))
_BRACKETS_2025 = ((0, 6_000, Decimal("0.19")), (6_000, 50_000, Decimal("0.21")),
                  (50_000, 200_000, Decimal("0.23")), (200_000, 300_000, Decimal("0.27")),
                  (300_000, None, Decimal("0.30")))

# Mapeo de casillas verificado: Renta 2025 (Orden HAC/277/2026).
CASILLAS_BASIS = "orden-hac-277-2026-renta-2025"
CASILLAS_YEARS = {2025}

# Casilla 0029: ingresos íntegros de rendimientos del capital mobiliario
# (dividendos). Casilla 0597: retenciones a cuenta españolas. Casilla 0588:
# deducción por doble imposición internacional (art. 80 LIRPF).
CASILLA_DIVIDENDOS = "0029"
CASILLA_RETENCIONES_ES = "0597"
CASILLA_DOBLE_IMPOSICION = "0588"

# Tope de convenio: España solo acredita la retención extranjera hasta el
# tipo del convenio de doble imposición; el exceso se reclama en origen.
# La mayoría de convenios de España limitan dividendos al 15 %: valor por
# defecto conservador, con entradas explícitas donde consta.
DEFAULT_TREATY_RATE = Decimal("0.15")
TREATY_DIVIDEND_RATES = {"US": Decimal("0.15")}

UNKNOWN_COUNTRY = "??"


def savings_bands(year: int) -> tuple:
    """Escala del ahorro vigente en ``year`` (tuplas desde/hasta/tipo)."""
    if year >= 2025:
        return _BRACKETS_2025
    if year >= 2023:
        return _BRACKETS_2023
    return _BRACKETS_2021


def calculate_savings_tax(income: Decimal, year: int) -> Decimal:
    """Cuota del ahorro progresiva sobre ``income`` (EUR) para ``year``."""
    if income <= 0:
        return Decimal("0")
    tax = Decimal("0")
    for lower, upper, rate in savings_bands(year):
        width = None if upper is None else Decimal(upper - lower)
        taxable = income - Decimal(lower)
        if taxable <= 0:
            break
        if width is not None:
            taxable = min(taxable, width)
        tax += taxable * rate
        if width is None or taxable < width:
            break
    return tax


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_casillas(dividends: list[dict], realized: list[dict], fiscal_year: int) -> dict:
    """Mapeo a casillas del Modelo 100 (Renta 2025, Orden HAC/277/2026).

    Solo ganancias/pérdidas por transmisión de acciones negociadas y
    dividendos; el resto de bloques del modelo no se tocan.

    Las ventas entran con su resultado COMPUTABLE del año (gain_base ya neto
    de la pérdida bloqueada por la regla de los 2 meses: lo bloqueado no es
    pérdida computable del ejercicio, se difiere al lote recomprado).
    Totales None cuando falta FX en algún componente (un total parcial
    parecería definitivo y sería incorrecto).
    """
    if fiscal_year not in CASILLAS_YEARS:
        return {
            "available": False,
            "basis": None,
            "unavailable_reason": (
                f"Mapeo de casillas verificado solo para la Renta 2025 "
                f"({CASILLAS_BASIS}); el ejercicio {fiscal_year} usa otra "
                "orden ministerial y no se muestran números sin verificar."
            ),
        }

    rows = []
    transmission = Decimal("0")
    acquisition = Decimal("0")
    gains = Decimal("0")
    losses = Decimal("0")
    incomplete = False
    for bucket in realized:
        for sale in bucket["sales"]:
            gain_base = sale["gain_base"]
            # Transmision/adquisicion convertidas con el tipo de la fecha de
            # venta, calculado en el motor FIFO (nunca derivado del resultado:
            # la regla de los 2 meses rompe la proporcionalidad).
            proceeds_base = sale.get("proceeds_base")
            cost_base = sale.get("cost_base")
            if gain_base is None or proceeds_base is None or cost_base is None:
                incomplete = True
            rows.append({
                "ticker": bucket["ticker"],
                "date": sale["date"],
                "transmission_base": _money(Decimal(str(proceeds_base))) if proceeds_base is not None else None,
                "acquisition_base": _money(Decimal(str(cost_base))) if cost_base is not None else None,
                "gain_base": _money(Decimal(str(gain_base))) if gain_base is not None else None,
            })
            if proceeds_base is not None:
                transmission += Decimal(str(proceeds_base))
            if cost_base is not None:
                acquisition += Decimal(str(cost_base))
            if gain_base is not None:
                if gain_base >= 0:
                    gains += Decimal(str(gain_base))
                else:
                    losses += abs(Decimal(str(gain_base)))

    dividends_total = sum(
        (Decimal(str(b["dividends_base"] or 0)) for b in dividends), Decimal("0")
    )
    dividend_incomplete = any(b["missing_fx"] for b in dividends)

    return {
        "available": True,
        "basis": CASILLAS_BASIS,
        "acciones_negociadas": {
            "pagina": "14 III (art. 37.1.a LIRPF)",
            "rows": rows,
            "0328_transmision_global": None if incomplete else _money(transmission),
            "0331_adquisicion_global": None if incomplete else _money(acquisition),
            "0339_suma_ganancias": None if incomplete else _money(gains),
            "0340_suma_perdidas": None if incomplete else _money(losses),
            "incomplete": incomplete,
        },
        "dividendos": {
            "0029_ingresos_integros": None if dividend_incomplete else _money(dividends_total),
            "incomplete": dividend_incomplete,
        },
        "notas": [
            "Todas las transmisiones del ledger se tratan como acciones "
            "negociadas en mercados regulados; opciones, cripto y fondos no "
            "cotizados irían a 'otros elementos patrimoniales' "
            "(1626/1633/1637) y no están soportados.",
            "La casilla 0327 es la denominación de los valores (texto), no "
            "un importe: en Renta Web se cumplimenta una fila por valor con "
            "los datos de 'rows'.",
        ],
    }


def build_double_taxation(
    dividends: list[dict],
    country_by_ticker: dict[str, str | None],
    fiscal_year: int,
    total_savings_base: Decimal | None = None,
) -> dict:
    """Deducción por doble imposición internacional (art. 80 LIRPF, casilla 0588).

    Por país: la deducción es el MENOR de (a) la retención extranjera
    soportada con tope en el tipo de convenio sobre el íntegro, y (b) la
    cuota española sobre esos rendimientos (tipo medio efectivo de la base
    del ahorro si se conoce; escala progresiva sobre el propio rendimiento
    en caso contrario).

    La retención de emisores españoles NO es deducible aquí: es un pago a
    cuenta doméstico (casilla 0597) y se devuelve aparte.
    País desconocido (sin domicile_country): bloque marcado
    ``manual_review``, sin deducción calculada.
    """
    by_country: dict[str, dict] = {}
    manual_review = []
    for bucket in dividends:
        gross = bucket["dividends_base"]
        withheld = bucket["withholding_base"]
        if bucket["missing_fx"]:
            manual_review.append({
                "ticker": bucket["ticker"],
                "reason": "Sin tipo de cambio para convertir el dividendo o la retención; no entra en la deducción.",
            })
            continue
        if not gross and not withheld:
            continue
        country = (country_by_ticker.get(bucket["ticker"]) or "").strip().upper()
        if country in {"", UNKNOWN_COUNTRY}:
            manual_review.append({
                "ticker": bucket["ticker"],
                "reason": "País de retención desconocido (sin domicilio del emisor); no se calcula deducción para este bloque.",
            })
            continue
        entry = by_country.setdefault(country, {"gross": Decimal("0"), "withheld": Decimal("0")})
        entry["gross"] += Decimal(str(gross or 0))
        entry["withheld"] += Decimal(str(withheld or 0))

    effective_rate = None
    if total_savings_base is not None and total_savings_base > 0:
        effective_rate = calculate_savings_tax(total_savings_base, fiscal_year) / total_savings_base

    countries = []
    total_deduction = Decimal("0")
    spanish_withholding = Decimal("0")
    incomplete = False
    for country in sorted(by_country):
        data = by_country[country]
        if country == "ES":
            # Retención a cuenta doméstica → casilla 0597, nunca crédito 0588.
            spanish_withholding += data["withheld"]
            continue
        if data["withheld"] <= 0:
            continue
        treaty_rate = TREATY_DIVIDEND_RATES.get(country, DEFAULT_TREATY_RATE)
        treaty_source = "convenio" if country in TREATY_DIVIDEND_RATES else "defecto-15%"
        spanish_tax = (
            data["gross"] * effective_rate
            if effective_rate is not None
            else calculate_savings_tax(data["gross"], fiscal_year)
        )
        creditable = min(data["withheld"], data["gross"] * treaty_rate)
        deduction = min(creditable, spanish_tax)
        if data["withheld"] > creditable:
            incomplete = True  # hay exceso reclamable en origen: se señala
        countries.append({
            "country": country,
            "gross_base": _money(data["gross"]),
            "withheld_base": _money(data["withheld"]),
            "treaty_rate": float(treaty_rate),
            "treaty_rate_source": treaty_source,
            "creditable_base": _money(creditable),
            "spanish_tax_base": _money(spanish_tax),
            "deduction_base": _money(deduction),
            "excess_reclaimable_base": _money(data["withheld"] - creditable),
        })
        total_deduction += deduction

    return {
        "casilla": CASILLA_DOBLE_IMPOSICION,
        "basis": "art-80-lirpf",
        "method": (
            "tipo-medio-efectivo" if effective_rate is not None
            else "escala-progresiva-por-pais"
        ),
        "countries": countries,
        "total_deduction_base": _money(total_deduction),
        "spanish_withholding_base": {
            "casilla": CASILLA_RETENCIONES_ES,
            "amount": _money(spanish_withholding),
        },
        "excess_withholding_reclaimable": incomplete,
        "manual_review": manual_review,
        "notas": [
            "El exceso de retención sobre el tipo de convenio no lo devuelve "
            "Hacienda: se reclama al fisco del país de origen (devolución del "
            "exceso de retención en origen).",
            "País de retención aproximado por el domicilio del emisor; con "
            "ISIN por valor se podrá verificar por prefijo.",
        ],
    }
