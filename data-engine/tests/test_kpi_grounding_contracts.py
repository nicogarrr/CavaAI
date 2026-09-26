"""Contracts for a reported KPI: locale, scale and grounding in its quote.

The defects these pin down were all invisible from the outside because the
value passed every existing check:

* the Spanish decimal comma was stripped, so a reported 3.456,7 millones
  became 3.456.700 (1000x below reality) and was published as a canonical fact;
* the scale multiplier was read from the value text, so a bare "b" inside a
  label turned a number into billions;
* a verbatim quote vouched for a figure it never mentioned, so `approve()`
  wrote a number the document never reported.
"""

import asyncio
import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.contracts import LLMRequest, LLMResponse, Message, Usage
from app.llm.routing import TaskModelRouter
from app.models.entities import (
    Base,
    Company,
    Document,
    DocumentChunk,
    KPIExtractionCandidate,
)
from app.services.kpi_extraction_service import KPIExtractionService
from app.services.number_parsing import find_number_tokens, parse_localized_number


LOCALE_TOKENS = [
    ("3.456,7", Decimal("3456.7")),
    ("0,24", Decimal("0.24")),
    ("1.234,56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("1,234", Decimal("1234")),
    ("1.250", Decimal("1250")),
    ("1.234.567", Decimal("1234567")),
    ("1,234,567", Decimal("1234567")),
    ("12,5", Decimal("12.5")),
    ("120.50", Decimal("120.50")),
    ("1 234,5", Decimal("1234.5")),
    ("(1.234,5)", Decimal("-1234.5")),
    ("-45,75", Decimal("-45.75")),
]


@pytest.mark.parametrize("raw,expected", LOCALE_TOKENS)
def test_locale_tokens_keep_their_magnitude(raw, expected):
    parsed = parse_localized_number(raw)
    assert parsed is not None, raw
    assert parsed[0] == expected


@pytest.mark.parametrize("raw", ["n/a", "12%", "1.2.3", "", "   "])
def test_unparseable_tokens_never_become_a_zero(raw):
    assert parse_localized_number(raw) is None


def test_tokenizer_keeps_the_figures_of_a_spanish_sentence_apart():
    # "en 2024, 1.234,5 millones" is TWO figures. Merging them on the comma and
    # the space yields 20241.2345, which then vouches for nothing.
    assert find_number_tokens("en 2024, 1.234,5 millones") == ["2024,", "1.234,5"]
    assert find_number_tokens("1 234 567,89") == ["1234567,89"]
    assert find_number_tokens("12,5 % 3") == ["12,5", "3"]


SCALED_VALUES = [
    # raw, unit, canonical unit, expected value
    ("3.456,7", "millones", "decimal", Decimal("3456700000")),
    ("3.456,7", "million", "USD", Decimal("3456700000")),
    ("2,5", "mil millones", "USD", Decimal("2500000000")),
    ("2,5", "billones", "USD", Decimal("2500000000000")),
    ("500", "miles de euros", "EUR", Decimal("500000")),
    ("1,2", "b", "USD", Decimal("1200000000")),
    ("26,461", "M", "USD", Decimal("26461000000")),
    ("12,5", "por ciento", "decimal", Decimal("0.125")),
    ("25", "%", "decimal", Decimal("0.25")),
    ("(1.250)", "thousand", "USD", Decimal("-1250000")),
    ("(1,250)", "thousand", "USD", Decimal("-1250000")),
    ("391", "billion USD", "USD", Decimal("391000000000")),
    ("1234567", "USD", "USD", Decimal("1234567")),
]


@pytest.mark.parametrize("raw,unit,canonical,expected", SCALED_VALUES)
def test_scale_comes_from_the_declared_unit(raw, unit, canonical, expected):
    value, meta = KPIExtractionService._normalize(raw, unit, canonical)
    assert value == expected, (raw, unit)
    assert meta["scale_source"] == "unit_only"


def test_value_text_never_invents_a_scale():
    # A label that happens to contain a scale letter is not a unit: the
    # multiplier is 1 and the figure is left as written.
    value, meta = KPIExtractionService._normalize("balance b", "USD", "USD")
    assert value is None
    value, meta = KPIExtractionService._normalize("4,2 B clientes", "USD", "USD")
    assert value == Decimal("4.2")
    assert meta["multiplier"] == "1"


def test_label_text_does_not_become_the_figure():
    # The fiscal year is part of the raw value, not the KPI.
    value, _ = KPIExtractionService._normalize("Ingresos FY24: 1.234,5", "M EUR", "decimal")
    assert value == Decimal("1234500000")


GROUNDED_QUOTE = (
    "Los ingresos del ejercicio 2024 ascendieron a 1.234,5 millones de euros, "
    "un 12,5% mas que en 2023."
)


def test_grounding_accepts_the_figures_the_quote_states():
    figures, stated = KPIExtractionService._value_in_quote(GROUNDED_QUOTE)
    assert stated is True
    assert Decimal("1234.5") in figures
    assert Decimal("12.5") in figures
    # The canonical value carries the multiplier the quote omits.
    assert KPIExtractionService._same_magnitude(Decimal("1234500000"), figures) is True
    # A percentage is stored as a decimal rate.
    assert KPIExtractionService._same_magnitude(Decimal("0.125"), figures) is True


def test_grounding_rejects_a_figure_the_quote_never_states():
    figures, _ = KPIExtractionService._value_in_quote(GROUNDED_QUOTE)
    assert KPIExtractionService._same_magnitude(Decimal("9999"), figures) is False
    # The 1000x error this service used to publish: 3.456.700 instead of
    # 3.456.700.000 is a real number, but not one the quote supports.
    assert KPIExtractionService._same_magnitude(Decimal("3456700"), figures) is False


def test_a_quote_without_figures_cannot_vouch_for_a_value():
    figures, stated = KPIExtractionService._value_in_quote("los ingresos del ejercicio")
    assert figures == set()
    assert stated is False


# --------------------------------------------------------------------------
# end to end: an ungrounded observation must not reach a canonical fact
# --------------------------------------------------------------------------


class _StaticProvider(LLMProvider):
    name = "test-provider"

    def __init__(self, payload):
        super().__init__(
            model_router=TaskModelRouter(default_model="test-model"),
            timeout_seconds=1,
            max_retries=0,
        )
        self.payload = payload

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            message=Message("assistant", json.dumps(self.payload)),
            usage=Usage(100, 50, 150, cache_read_tokens=20),
            model="test-model",
            provider=self.name,
            request_id="test-request",
        )


def _extraction(chunk_text: str, raw_value: str) -> KPIExtractionCandidate:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(
            ticker="ASTS", name="ASTS Test", exchange="TEST", currency="USD",
            sector="Test", industry="Test", company_type="space_telecom_pre_fcf",
            valuation_model="space_pre_revenue_dcf", special_sources=[],
            special_risks=[], factor_tags=["space", "telecom"],
        )
        db.add(company)
        db.flush()
        document = Document(
            company_id=company.id, title="FY2025 update", source_type="company_ir"
        )
        db.add(document)
        db.flush()
        chunk = DocumentChunk(document_id=document.id, chunk_index=0, text=chunk_text)
        db.add(chunk)
        db.commit()

        provider = _StaticProvider(
            {
                "observations": [
                    {
                        "metric_key": "penetration",
                        "raw_label": "Penetration",
                        "raw_value": raw_value,
                        "raw_unit": "percent",
                        "period": "FY2025",
                        "fiscal_year": 2025,
                        "fiscal_quarter": "FY",
                        "chunk_id": chunk.id,
                        "quote": chunk_text,
                        "confidence": 0.95,
                    }
                ]
            }
        )
        candidates = asyncio.run(
            KPIExtractionService(provider).extract_document(db, document)
        )
        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate.trace["locator_verified"] is True  # the sentence is real
        if candidate.status == "needs_review":
            with pytest.raises(ValueError, match="pending candidates"):
                KPIExtractionService().approve(db, candidate, actor="analyst")
        return candidate


def test_a_verbatim_quote_cannot_vouch_for_a_figure_it_never_states():
    # Locator verification passes: the sentence IS in the chunk. The reported
    # 38.7% is nowhere in it, so the candidate must not be approvable.
    candidate = _extraction("Penetration reached 12.5% in FY2025.", "38.7%")
    assert candidate.normalized_value == Decimal("0.387")
    assert candidate.reconciliation_status == "needs_review"
    assert candidate.trace["value_grounded"] is False
    assert candidate.trace["figures_in_quote"] == ["12.5", "2025"]


def test_a_quote_without_a_figure_cannot_vouch_for_a_value():
    candidate = _extraction("Penetration was not disclosed for FY2025.", "12.5%")
    assert candidate.reconciliation_status == "needs_review"
    assert candidate.trace["value_grounded"] is False
    assert candidate.trace["figures_in_quote"] == ["2025"]


def test_a_grounded_figure_stays_approvable():
    candidate = _extraction("Penetration reached 12.5% in FY2025.", "12.5%")
    assert candidate.normalized_value == Decimal("0.125")
    assert candidate.reconciliation_status == "reconciled"
    assert candidate.status == "pending_approval"
    assert candidate.trace["value_grounded"] is True
