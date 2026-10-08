import asyncio

import pytest

from app.llm import LLMRequest, LLMResponse, Message, Usage
from app.services import llm_output_guard as g

CLEAN = (
    "La compania mantiene un margen operativo estable y el flujo de caja libre "
    "cubre el dividendo. El EBITDA y el ROIC apuntan a una valoracion razonable."
)


def _resp(text):
    return LLMResponse(message=Message("assistant", text), usage=Usage(1, 1), model="m", provider="p")


class Fake:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    async def complete(self, request):
        self.calls.append(request)
        return _resp(self.texts.pop(0))


def _req():
    return LLMRequest(messages=[Message("system", "s"), Message("user", "u")])


@pytest.fixture(autouse=True)
def _reset():
    g.reset_guard_stats()


def test_clean_text_passes_untouched():
    assert g.inspect_text(CLEAN) == []
    p = Fake(CLEAN)
    out = asyncio.run(g.complete_guarded(p, _req(), source="t"))
    assert out.response.text == CLEAN and not out.retried and len(p.calls) == 1
    assert g.guard_stats()["t.calls"] == 1 and "t.triggered" not in g.guard_stats()


def test_quoted_english_and_financial_terms_are_ignored():
    text = 'El CEO dijo "the company will grow" y el free cash flow, el P/E y el EBITDA mejoran.'
    assert g.inspect_text(text) == []


def test_cjk_detected():
    assert g.REASON_CJK in g.inspect_text("La empresa tiene una buena 문화 interna.")
    assert g.REASON_CJK in g.inspect_text("margen 利润 estable")


def test_mixed_english_detected():
    text = "Therefore the margin is stable, which is provided that the demand will hold."
    assert g.REASON_ENGLISH in g.inspect_text(text)


def test_corrupt_tokens_detected():
    assert g.REASON_CORRUPT in g.inspect_text("La valoracion es múltijodepends de otros factores.")
    assert g.REASON_CORRUPT in g.inspect_text("Los se-components? del indice suben.")
    assert g.REASON_CORRUPT in g.inspect_text("Texto con \ufffd roto")


def test_json_keys_do_not_count_only_values():
    assert (
        g.inspect_response_text('{"summary": "Margen estable y caja neta.", "insufficient_data": false}')
        == []
    )
    assert g.REASON_CJK in g.inspect_response_text('{"summary": "Margen 문화 estable"}')


def test_cjk_triggers_one_retry_then_recovers():
    p = Fake("Margen estable 문화.", CLEAN)
    out = asyncio.run(g.complete_guarded(p, _req(), source="t"))
    assert out.retried and out.response.text == CLEAN and len(out.discarded) == 1
    assert len(p.calls) == 2
    assert "REINTENTO" in p.calls[1].messages[0].content
    s = g.guard_stats()
    assert s["t.triggered"] == 1 and s["t.recovered"] == 1 and s["t.reason.cjk"] == 1


def test_mixed_english_triggers_retry():
    bad = "However the company is strong, which is because the demand will grow and the margin is high."
    p = Fake(bad, CLEAN)
    out = asyncio.run(g.complete_guarded(p, _req(), source="t"))
    assert out.retried and len(p.calls) == 2


def test_failed_retry_raises_and_counts_rejection():
    p = Fake("Margen 문화.", "Otra vez 문화.")
    with pytest.raises(g.LLMOutputRejected) as exc:
        asyncio.run(g.complete_guarded(p, _req(), source="t"))
    assert exc.value.reasons == [g.REASON_CJK] and len(p.calls) == 2
    assert g.guard_stats()["t.rejected"] == 1


def test_english_off_ignores_english_but_not_cjk():
    text = "However the company is strong, which is because the demand will grow and the margin is high."
    assert g.inspect_text(text, english="off") == []
    assert g.REASON_CJK in g.inspect_text(text + " 문화", english="off")


def test_thesis_debate_degrades_when_guard_rejects(monkeypatch):
    from app.services import thesis_debate_service as svc

    p = Fake(*(["Texto 문화 roto."] * 2))
    with pytest.raises(g.LLMOutputRejected):
        asyncio.run(
            svc._complete_text(p, system="s", user="u", task="red_team", max_tokens=10, temperature=0.1)
        )
