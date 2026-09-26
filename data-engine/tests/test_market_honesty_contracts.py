"""Contract tests for the market-data and alert honesty rules.

Three defects that turned "no data" into a real-looking number:

* the FMP branch of the market refresh stamped the LAST TRADED close with
  `as_of`. A Sunday refresh wrote a Sunday bar holding Friday's close, so
  market_movers reported a 0.00% move that never happened and `age_days` came
  out as 0, silently disabling the staleness guard for every alert on it.
* the refresh also wrote `open = high = low = close = adj_close = spot`, so a
  spot price masqueraded as a daily bar and claimed an adjustment that was
  never performed. Every total return, beta and Sharpe over a history
  containing a split or a dividend is computed on that column.
* the insider read returned `status: "ok"` with an empty signal list when all
  filings failed, which reads as "no insider activity" and produces a false
  all-clear.
"""

from datetime import date, datetime

import pytest

from app.services.alert_rule_service import _OPERATORS, AlertRuleService
from app.services.insider_service import _is_c_suite, _is_ceo, _is_cfo
from app.services.market_refresh_service import _provider_date


# --------------------------------------------------------------------------
# a quote without a date is not a quote for today
# --------------------------------------------------------------------------


def test_provider_date_reads_an_iso_date():
    assert _provider_date({"date": "2026-09-25"}, date(2026, 9, 27)) == date(2026, 9, 25)


def test_provider_date_reads_a_datetime():
    item = {"date": "2026-09-25T21:00:00Z"}
    assert _provider_date(item, date(2026, 9, 27)) == date(2026, 9, 25)


def test_provider_date_reads_a_unix_timestamp():
    stamp = int(datetime(2026, 9, 25, 20, 0).timestamp())
    assert _provider_date({"date": stamp}, date(2026, 9, 27)) == date(2026, 9, 25)


@pytest.mark.parametrize("item", [{}, {"date": None}, {"date": ""}, {"other": "x"}])
def test_provider_date_returns_none_when_the_provider_gives_none(item):
    """No date means the observation must be skipped, not mis-dated."""
    assert _provider_date(item, date(2026, 9, 27)) is None


def test_a_friday_close_is_not_stamped_with_the_sunday():
    """The regression: a Sunday refresh used to write a Sunday bar."""
    sunday = date(2026, 9, 27)
    friday_close_date = _provider_date({"date": "2026-09-25"}, sunday)
    assert friday_close_date == date(2026, 9, 25)
    assert friday_close_date != sunday


# --------------------------------------------------------------------------
# insider titles: whole-title match, not substring
# --------------------------------------------------------------------------


def test_a_vice_president_is_not_the_ceo():
    """'president' is a substring of 'Vice President, Human Resources'."""
    tx = {"officer_title": "Vice President, Human Resources", "role": "officer"}
    assert _is_ceo(tx) is False
    assert _is_c_suite(tx) is False


def test_a_vice_president_of_finance_is_not_the_cfo():
    tx = {"officer_title": "Vice President, Finance", "role": "officer"}
    assert _is_cfo(tx) is False
    assert _is_c_suite(tx) is False


@pytest.mark.parametrize(
    "title",
    [
        "Chief Executive Officer",
        "CEO",
        "President and Chief Executive Officer",
        "Chairman and CEO",
    ],
)
def test_a_real_ceo_is_recognised(title):
    tx = {"officer_title": title, "role": "director"}
    assert _is_ceo(tx) is True
    assert _is_c_suite(tx) is True


@pytest.mark.parametrize(
    "title", ["Chief Financial Officer", "CFO", "Vice President and CFO"]
)
def test_a_real_cfo_is_recognised(title):
    tx = {"officer_title": title, "role": "officer"}
    assert _is_cfo(tx) is True


def test_a_plain_shareholder_is_not_c_suite():
    tx = {"officer_title": "", "role": "10% owner"}
    assert _is_c_suite(tx) is False


def test_an_absent_title_is_not_c_suite():
    assert _is_c_suite({}) is False


# --------------------------------------------------------------------------
# alert operators
# --------------------------------------------------------------------------


def test_non_numeric_values_never_order_by_ascii():
    """'1,234' < '1000' used to be decided by ASCII order, inverting the sign."""
    service = AlertRuleService()
    assert service._matches("1,234", "<", "1000") is False
    assert service._matches("1,234", ">", "1000") is False


def test_non_numeric_values_still_compare_by_equality():
    service = AlertRuleService()
    assert service._matches("ACME", "==", "ACME") is True
    assert service._matches("ACME", "!=", "ACME") is False


def test_numeric_comparisons_still_work():
    service = AlertRuleService()
    assert service._matches(190.0, ">", 100) is True
    assert service._matches(90.0, "<", 100) is True
    assert service._matches(100.0, ">=", 100) is True
    assert service._matches(100.0, "<=", 100) is True
    assert service._matches(100.0, "==", 100) is True
    assert service._matches(100.0, "!=", 101) is True


def test_inequality_is_a_supported_operator():
    assert "!=" in _OPERATORS


def test_an_unknown_operator_never_matches():
    service = AlertRuleService()
    assert service._matches(100.0, "~=", 100) is False
    assert service._matches(100.0, "contains", 100) is False


def test_a_none_observation_never_matches():
    service = AlertRuleService()
    assert service._matches(None, ">", 0) is False
