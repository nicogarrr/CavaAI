"""Tests del triage Jev: sin key no-op, ajustes de materiality, nunca rompe."""
import asyncio
from unittest.mock import patch

from app.services import jev_triage_service as jts
from app.services.jev_triage_service import (
    JevTriageResult,
    apply_to_materiality,
    classify_urgency_sync,
)


def _drive(coro):
    """Ejecuta la corrutina en un loop dedicado (evita 'never awaited')."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_no_key_returns_none(monkeypatch):
    jts.get_settings.cache_clear() if hasattr(jts.get_settings, "cache_clear") else None
    with patch.object(jts, "get_settings") as gs:
        gs.return_value.typesafe_api_key = None
        assert classify_urgency_sync("texto") is None


def test_classify_with_fake_client():
    class FakeDecision:
        label = "urgent"
        confidence = 0.93
        probabilities = {}
        model = "jev"
        latency_s = 0.01

    class FakeClient:
        async def classify(self, *a, **k):
            return FakeDecision()

    with patch.object(jts, "build_client", return_value=FakeClient()), patch(
        "asyncio.run", side_effect=_drive
    ):
        result = classify_urgency_sync("fraude contable, el valor se desploma")
    assert result is not None and result.label == "urgent" and result.confidence >= 0.9


def test_classify_error_is_soft():
    class BrokenClient:
        async def classify(self, *a, **k):
            raise RuntimeError("boom")

    with patch.object(jts, "build_client", return_value=BrokenClient()):
        result = classify_urgency_sync("anything")
    assert result is not None and result.error and "RuntimeError" in result.error and not result.applied


def test_apply_urgent_bump():
    t = JevTriageResult("urgent", 0.90, False, 0.1)
    reasons = []
    assert apply_to_materiality(5, reasons, t) == 6
    assert any("jev_urgent" in r for r in reasons)


def test_apply_routine_discount():
    t = JevTriageResult("routine", 0.95, False, 0.1)
    reasons = []
    assert apply_to_materiality(5, reasons, t) == 4
    assert any("jev_routine" in r for r in reasons)


def test_apply_low_confidence_noop():
    t = JevTriageResult("urgent", 0.5, False, 0.1)
    assert apply_to_materiality(5, [], t) == 5
    t2 = JevTriageResult("routine", 0.7, False, 0.1)
    assert apply_to_materiality(5, [], t2) == 5


def test_materiality_applies_jev_hook_and_opt_out():
    from app.services.materiality_service import MaterialityService

    svc = MaterialityService()
    urgent = JevTriageResult("urgent", 0.90, False, 0.1)
    with patch.object(jts, "classify_urgency_sync", return_value=urgent):
        hooked = svc.assess_news(None, None, "fraude contable grave", "feed", None)
        silent = svc.assess_news(None, None, "fraude contable grave", "feed", None, use_jev=False)
    assert hooked.materiality_score == silent.materiality_score + 1
    assert any("jev_urgent" in r for r in hooked.reasons)
    assert not any("jev_" in r for r in silent.reasons)
    with patch.object(jts, "classify_urgency_sync", return_value=None):
        no_key = svc.assess_news(None, None, "fraude contable grave", "feed", None)
    assert no_key.materiality_score == silent.materiality_score
