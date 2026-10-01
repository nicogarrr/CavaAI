import asyncio

from app.llm import ProviderResponseError
from app.services import thesis_narrative_llm as mod


class _Provider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def complete(self, request):
        self.calls += 1
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


def test_empty_content_retries_once_then_succeeds():
    p = _Provider([ProviderResponseError("x returned an empty assistant message"), "ok"])
    assert asyncio.run(mod._call_with_empty_retry(p, lambda: object())) == "ok"
    assert p.calls == 2


def test_empty_content_retries_only_once():
    e = ProviderResponseError("x returned an empty assistant message")
    p = _Provider([e, e, "never"])
    try:
        asyncio.run(mod._call_with_empty_retry(p, lambda: object()))
        raise AssertionError("debia propagar")
    except ProviderResponseError:
        pass
    assert p.calls == 2


def test_other_errors_are_not_retried():
    p = _Provider([ValueError("boom"), "never"])
    try:
        asyncio.run(mod._call_with_empty_retry(p, lambda: object()))
        raise AssertionError("debia propagar")
    except ValueError:
        pass
    assert p.calls == 1


def test_default_fallback_is_disabled():
    from app.core.config import Settings

    assert Settings(_env_file=None).opencode_go_fallback_model == ""
