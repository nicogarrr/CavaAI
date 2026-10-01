from datetime import date

from app.services.financial_ingestion_service import _latest_filed_date


def test_latest_filed_date_picks_max():
    us = {"Revenues": {"units": {"USD": [{"filed": "2026-03-02"}, {"filed": "2026-08-10"}, {"filed": "bad"}]}},
          "Assets": {"units": {"USD": [{"filed": "2025-03-03"}]}}}
    assert _latest_filed_date(us) == date(2026, 8, 10)


def test_latest_filed_date_none_without_data():
    assert _latest_filed_date({}) is None
    assert _latest_filed_date({"X": {"units": {"USD": [{}]}}}) is None
