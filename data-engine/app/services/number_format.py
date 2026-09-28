"""Cifras visibles para el usuario en español (es-ES).

Réplica backend de ``formatCompact`` de ``lib/format.ts``: millones como
"M" y miles de millones como "mil M", con coma decimal y punto de miles.
Estos textos se persisten en claims y resúmenes de alertas: deben nacer ya
legibles, no depender de que cada consumidor formatee.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

NumericLike = int | float | Decimal | str | None


def _to_decimal(value: NumericLike) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def format_number_es(value: NumericLike, maximum_fraction_digits: int = 2) -> str | None:
    """Número con separadores es-ES (1.234,56). None si no es numérico."""
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    text = f"{parsed:,.{maximum_fraction_digits}f}"
    # en-US (coma de miles, punto decimal) -> es-ES (punto de miles, coma).
    text = text.replace(",", "@").replace(".", ",").replace("@", ".")
    if "," in text:
        text = text.rstrip("0").rstrip(",")
    return text


def format_compact_es(value: NumericLike, maximum_fraction_digits: int = 2) -> str | None:
    """Cifra compacta es-ES: 200966000000 -> "200,97 mil M"; 24000000 -> "24 M".

    La escala se fija siempre (M / mil M) porque Intl es-ES con notation
    "compact" es inconsistente para miles de millones. None si no es numérico.
    """
    parsed = _to_decimal(value)
    if parsed is None:
        return None
    abs_value = abs(parsed)
    if abs_value >= Decimal("1e9"):
        scaled = format_number_es(parsed / Decimal("1e9"), maximum_fraction_digits)
        return f"{scaled} mil M"
    if abs_value >= Decimal("1e6"):
        scaled = format_number_es(parsed / Decimal("1e6"), maximum_fraction_digits)
        return f"{scaled} M"
    return format_number_es(parsed, maximum_fraction_digits)
