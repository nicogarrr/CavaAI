"""Serializacion de valores XBRL para snapshots SEC (sin dependencias pesadas)."""

from __future__ import annotations


def entry_value(raw):
    """Preserva decimales: int() truncaba BPA (7,26 -> 7) y ratios (B19).

    Los importes enteros (revenue en dolares) siguen serializandose como int;
    cualquier valor con fraccion se conserva como float.
    """
    if raw is None:
        return None
    number = float(raw)
    return int(number) if number.is_integer() else number
