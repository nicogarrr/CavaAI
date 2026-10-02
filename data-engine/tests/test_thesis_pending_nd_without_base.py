"""Supuestos sin base documentada salen como N/D en datos pendientes, no como INFERIDO."""

from app.services.thesis_service import ThesisService


def _ltm(basis=None):
    return {
        "assumptions": {
            "wacc": {"value": 0.1, "unit": "decimal", "source_type": "llm_estimate",
                     "basis": basis, "source_fact_ids": [], "confidence": 0.5},
        }
    }


def test_assumption_without_base_listed_as_nd():
    md = ThesisService()._pendings_markdown({}, _ltm(), {})
    assert "N/D" in md and "wacc" in md


def test_pendings_empty_without_assumptions():
    md = ThesisService()._pendings_markdown({}, {}, {})
    assert "Sin datos pendientes" in md
