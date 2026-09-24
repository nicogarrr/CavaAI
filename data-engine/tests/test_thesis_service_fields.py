"""ThesisService professional-field contract tests.

The thesis is the product's centerpiece: hypothesis, invalidation
criteria, catalysts, rating, confidence and executive summary must be
derived deterministically from model data - never invented - and must
degrade to honest "en formacion" states when inputs are missing.
"""

from app.models.entities import Company
from app.services.thesis_service import ThesisService


def _company() -> Company:
    return Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )


# -- confidence score -----------------------------------------------------------

def test_confidence_score_ladder():
    service = ThesisService()
    assert service._confidence_score({"status": "insufficient_data"}, {"f": 1}) == 15
    assert service._confidence_score({"status": "ok"}, {}) == 25
    assert service._confidence_score({"publishable": True}, {"f": 1}) == 85
    assert service._confidence_score({"publishable": False}, {"f": 1}) == 55


# -- hypothesis -------------------------------------------------------------------

def test_hypothesis_honest_when_inputs_missing():
    service = ThesisService()
    text = service._hypothesis(_company(), {"current_price": None})
    assert "faltan datos" in text
    assert "Hipotesis en formacion" in text


def test_hypothesis_below_base_with_reverse_dcf():
    service = ThesisService()
    valuation = {
        "current_price": 150.0,
        "base_value": 200.0,
        "margin_of_safety": 0.25,
        "reverse_dcf": {"required_revenue_growth": 0.082},
    }
    text = service._hypothesis(_company(), valuation)
    assert "150.00" in text and "200.00" in text
    assert "25% por debajo" in text
    assert "8.2% anual" in text
    assert "Apple" in text


def test_hypothesis_above_base_without_growth():
    service = ThesisService()
    valuation = {
        "current_price": 250.0,
        "base_value": 200.0,
        "margin_of_safety": -0.25,
    }
    text = service._hypothesis(_company(), valuation)
    assert "25% por encima" in text
    assert "reverse DCF" not in text


# -- catalysts ---------------------------------------------------------------------

def test_catalysts_only_from_dated_earnings():
    service = ThesisService()
    evidence = {
        "sources": {
            "earnings": {
                "status": "ok",
                "next_date": "2026-10-29",
                "time": "amc",
                "eps_forecast": 1.6,
            }
        }
    }
    catalysts = service._catalysts(evidence)
    assert len(catalysts) == 1
    assert catalysts[0]["date"] == "2026-10-29"
    assert catalysts[0]["source"] == "earnings_calendar"
    assert catalysts[0]["time"] == "amc"
    assert catalysts[0]["eps_forecast"] == 1.6
    # Undated or failed earnings never produce a catalyst.
    assert service._catalysts({"sources": {"earnings": {"status": "error"}}}) == []
    assert service._catalysts({}) == []


# -- invalidation criteria ----------------------------------------------------------

def test_invalidation_criteria_from_model_data():
    service = ThesisService()
    valuation = {
        "margin_of_safety": 0.2,
        "base_value": 200.0,
        "reverse_dcf": {"required_revenue_growth": 0.08},
        "moat": {"moats": [{"type": "switching_costs", "trend": "declining"}]},
    }
    criteria = service._invalidation_criteria(_company(), valuation)
    assert len(criteria) == 3
    assert any("200.00" in c for c in criteria)
    assert any("8.0% anual" in c for c in criteria)
    assert any("switching_costs" in c for c in criteria)


def test_invalidation_criteria_honest_fallback():
    service = ThesisService()
    criteria = service._invalidation_criteria(_company(), {})
    assert criteria == [
        "Tesis en formacion: sin criterios automaticos hasta completar la valoracion."
    ]


# -- scenario probabilities ------------------------------------------------------------

def test_scenario_probabilities_extracted_or_none():
    service = ThesisService()
    model = {
        "scenarios": {
            "bear": {"probability": 0.2},
            "base": {"probability": 0.55},
            "bull": {"probability": 0.25},
            "junk": {"no_probability": True},
        }
    }
    assert service._scenario_probabilities(model) == {
        "bear": 0.2, "base": 0.55, "bull": 0.25,
    }
    assert service._scenario_probabilities({}) is None
    assert service._scenario_probabilities({"scenarios": {"x": {}}}) is None


# -- rating -------------------------------------------------------------------------

def test_rating_matrix():
    service = ThesisService()
    assert service._rating(0.5, True, "insufficient_data") == "insufficient_data"
    assert service._rating(0.5, False, "ok") == "blocked"
    assert service._rating(None, True, "ok") == "incomplete_price"
    assert service._rating(0.31, True, "ok") == "attractive"
    assert service._rating(-0.21, True, "ok") == "expensive"
    assert service._rating(0.0, True, "ok") == "watch"


# -- executive summary ----------------------------------------------------------------

def test_executive_summary_never_publishes_unsourced_value():
    service = ThesisService()
    valuation = {
        "status": "insufficient_data",
        "missing_inputs": ["revenue", "shares"],
        "trace": {"engine": "dcf_v2"},
    }
    text = service._executive_summary(_company(), valuation)
    assert "NOT PUBLISHABLE" in text
    assert "revenue, shares" in text
    assert "dcf_v2" in text


def test_executive_summary_partial_is_indicative_not_final():
    service = ThesisService()
    valuation = {
        "status": "partial",
        "missing_inputs": ["beta"],
        "trace": {"engine": "dcf_v2"},
    }
    text = service._executive_summary(_company(), valuation)
    assert "PARTIAL-INDICATIVE" in text
    assert "Not a final fair value" in text
    assert "beta" in text


# -- card summary (tarjeta "Ultima tesis") ---------------------------------------

def test_card_summary_is_readable_spanish_hypothesis():
    service = ThesisService()
    valuation = {
        "status": "ok",
        "current_price": 336.56,
        "base_value": 106.85,
        "margin_of_safety": -0.68,
        "reverse_dcf": {"required_revenue_growth": 0.35},
    }
    hypothesis = service._hypothesis(_company(), valuation)
    summary = service._card_summary(_company(), valuation, hypothesis)
    assert summary == hypothesis
    assert "por encima del escenario base" in summary
    assert "bucket" not in summary  # la jerga de motor no va a la tarjeta


def test_card_summary_insufficient_data_honest_spanish():
    service = ThesisService()
    valuation = {"status": "insufficient_data", "missing_inputs": ["revenue", "fcf"]}
    summary = service._card_summary(_company(), valuation, "hipotesis")
    assert "no publicable" in summary
    assert "revenue, fcf" in summary
    assert "NOT PUBLISHABLE" not in summary


def test_card_summary_partial_keeps_hypothesis_plus_caveat():
    service = ThesisService()
    valuation = {"status": "partial", "missing_inputs": ["shares_diluted"]}
    summary = service._card_summary(_company(), valuation, "Hipotesis X.")
    assert summary.startswith("Hipotesis X.")
    assert "parcial-indicativa" in summary
    assert "shares_diluted" in summary
