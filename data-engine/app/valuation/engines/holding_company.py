"""Holding-company engine — NAV / SOTP with explicit holding discount.

Supuestos: hereda todo de SOTPEngine (NAV por segmentos con múltiplos de
facts y descuento holding explícito). Ver SOTPEngine para el detalle de
escenarios bear/base/bull y la tabla de sensibilidad del descuento.
"""

from __future__ import annotations

from app.valuation.engines.sotp_engine import SOTPEngine


class HoldingCompanyEngine(SOTPEngine):
    """Holdings (BN/BABA-like): SOTP con descuento holding explícito.

    Supuestos: idénticos a SOTPEngine; el descuento recoge el conglomerate
    discount persistente. Misma tabla de sensibilidad del descuento.
    """

    key = "holding_company"
