"""Cliente TypeSafe Jev: classify() devuelve etiqueta calibrada sin red real."""
import asyncio
import json

import httpx
import pytest

from app.llm.jev import JevDecisionClient

FAKE_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "urgency": {
            "type": "choice",
            "choice": "routine",
            "confidence": 0.89,
            "probabilities": {"routine": 0.95, "urgent": 0.05},
        }
    },
    "usage": {"input_tokens": 328, "output_tokens": 32},
}


def _client(status: int = 200, payload: dict | None = None) -> JevDecisionClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"].startswith("Bearer ")
        assert request.url.path == "/v1/systemone"
        body = json.loads(request.content.decode())
        assert body["model"] and body["state"] and body["questions"]
        return httpx.Response(status, json=payload if payload is not None else FAKE_RESPONSE)

    transport = httpx.MockTransport(handler)
    return JevDecisionClient(api_key="test-key", client=httpx.AsyncClient(transport=transport))


def test_classify_returns_label_and_calibrated_confidence():
    decision = asyncio.run(_client().classify(
        "El oro cotiza plano",
        "urgency",
        "How urgent?",
        {"urgent": "crash", "routine": "mild"},
    ))
    assert decision.label == "routine"
    assert decision.confidence == pytest.approx(0.89)
    assert decision.probabilities["routine"] == pytest.approx(0.95)
    assert decision.model == "jev-1.13.0"
    assert decision.latency_s >= 0.0


def test_systemone_sends_model_state_questions():
    result = asyncio.run(_client().systemone({"message": "hola"}, {"q": {"type": "noul", "instructions": "?"}}))
    assert result["answers"]["urgency"]["choice"] == "routine"
    assert result["usage"]["input_tokens"] == 328


def test_server_error_raises_after_retries():
    client = _client(status=500, payload={"detail": "boom"})
    with pytest.raises(RuntimeError, match="after retries"):
        asyncio.run(client.systemone({"m": "x"}, {"q": {"type": "noul", "instructions": "?"}}, model="jev-latest"))
