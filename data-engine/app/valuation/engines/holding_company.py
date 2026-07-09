"""Holding-company engine — NAV / SOTP with explicit holding discount."""

from __future__ import annotations

from app.valuation.engines.sotp_engine import SOTPEngine


class HoldingCompanyEngine(SOTPEngine):
    """Alias engine for BN / BABA-style holding companies."""

    key = "holding_company"
