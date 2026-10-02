"""Cesta AI<>Biology (watchlist): identidad verificada contra SEC EDGAR.

CIK y nombre: https://www.sec.gov/files/company_tickers.json (consultado 2026-10-02).
Bolsa y SIC: https://data.sec.gov/submissions/CIK<cik>.json (2026-10-02).
"""

import pytest

from app.data.company_master import COMPANY_MASTER
from app.models import Company
from app.valuation.engines.registry import resolve_engine_key

SEC_IDENTITY = {
    "IBRX": ("1326110", "ImmunityBio"),
    "NAUT": ("1808805", "Nautilus Biotechnology"),
    "RXRX": ("1601830", "Recursion Pharmaceuticals"),
    "ABCL": ("1703057", "AbCellera Biologics"),
}


@pytest.mark.parametrize("ticker", sorted(SEC_IDENTITY))
def test_ticker_resolves_to_the_sec_registrant(ticker):
    rows = [row for row in COMPANY_MASTER if row["ticker"] == ticker]
    assert len(rows) == 1
    cik, name = SEC_IDENTITY[ticker]
    assert rows[0]["cik"] == cik
    assert rows[0]["name"] == name
    assert rows[0]["exchange"] == "NASDAQ"
    assert rows[0]["ir_url"].startswith("https://")


def test_master_has_no_duplicate_tickers_or_ciks():
    tickers = [row["ticker"] for row in COMPANY_MASTER]
    ciks = [row["cik"] for row in COMPANY_MASTER if row.get("cik")]
    assert len(tickers) == len(set(tickers))
    assert len(ciks) == len(set(ciks))


@pytest.mark.parametrize("ticker", sorted(SEC_IDENTITY))
def test_loss_making_biotechs_use_the_scenario_engine(ticker):
    row = next(r for r in COMPANY_MASTER if r["ticker"] == ticker)
    company = Company(**row)
    assert resolve_engine_key(company) == "pre_revenue"
