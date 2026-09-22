"""EarningsWorkflowService deterministic extraction contract tests.

Extracted metrics are always staged as candidate_pending_reconciliation
(never auto-applied), scaling is explicit, and tone is a transparent
lexical score - the deterministic base the thesis review relies on.
"""

from decimal import Decimal

from app.services.earnings_service import (
    EarningsWorkflowService,
    _scaled_value,
)


def test_scaled_value_margins_become_decimals():
    assert _scaled_value("45.5", "%", "gross_margin") == Decimal("0.455")
    assert _scaled_value("12", None, "operating_margin") == Decimal("0.12")


def test_scaled_value_money_scales():
    assert _scaled_value("123.4", "billion", "revenue") == Decimal("123400000000.0")
    assert _scaled_value("2.5", "bn", "revenue") == Decimal("2500000000.0")
    assert _scaled_value("900", "million", "revenue") == Decimal("900000000")
    assert _scaled_value("900", "m", "revenue") == Decimal("900000000")
    assert _scaled_value("42", None, "revenue") == Decimal("42")


def test_extract_metrics_stages_candidates_with_source_document():
    service = EarningsWorkflowService()
    doc_text = "Total revenue was $123.4 billion driven by services. Gross margin of 45.5%."
    metrics = service._extract_metrics(doc_text, {7: doc_text})
    by_metric = {item["metric"]: item for item in metrics}

    revenue = by_metric["revenue"]
    assert revenue["value"] == "123400000000.0"
    assert revenue["unit"] == "USD"
    assert revenue["status"] == "candidate_pending_reconciliation"
    assert revenue["source_document_id"] == 7
    assert "revenue" in revenue["quote"].lower()

    margin = by_metric["gross_margin"]
    assert margin["value"] == "0.455"
    assert margin["unit"] == "decimal"
    assert margin["status"] == "candidate_pending_reconciliation"

    # One candidate per metric at most (first match wins).
    assert sum(1 for m in metrics if m["metric"] == "revenue") == 1
    # Metrics absent from the text are omitted, never invented.
    assert "free_cash_flow" not in by_metric


def test_extract_metrics_marks_unknown_source_document():
    service = EarningsWorkflowService()
    metrics = service._extract_metrics("Net income reached $25 billion", {1: "other text"})
    assert metrics[0]["metric"] == "net_income"
    assert metrics[0]["source_document_id"] is None


def test_tone_lexical_contract():
    service = EarningsWorkflowService()
    positive = service._tone("Strong results, record revenue, improving outlook")
    assert positive["label"] == "positive"
    assert positive["positive_markers"] >= 3
    assert positive["method"] == "lexical_tone_v1"

    negative = service._tone("Weak demand and lowered guidance")
    assert negative["label"] == "negative"
    assert negative["negative_markers"] >= 2

    neutral = service._tone("")
    assert neutral["label"] == "neutral"
    assert neutral["score"] == 0
