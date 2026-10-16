"""No real network: adversarial slow-primary canaries use the real factory/adapter."""
import asyncio
import json

import httpx
import pytest

from app.core.config import Settings
from app.llm import LLMRequest, Message, create_llm_provider
from app.llm.errors import ProviderTransportError

PRIMARY = 'deepseek-v4.1-flash-free'
FALLBACK = 'space-bunny-free'
BODY = {
    'choices': [{'message': {'content': 'ok'}, 'finish_reason': 'stop'}],
    'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
}


def provider(client, fallback=FALLBACK, retries=2):
    return create_llm_provider(Settings(
        _env_file=None,
        opencode_go_api_key='test-secret',
        opencode_go_base_url='https://opencode.test/v1',
        opencode_go_model=PRIMARY,
        opencode_go_fallback_model=fallback,
        llm_total_timeout_seconds=0.3,
        llm_timeout_seconds=30,
        llm_max_retries=retries,
    ), client=client)


def request():
    return LLMRequest(messages=[Message('user', 'x')], cache=False)


def test_slow_primary_is_cancelled_and_real_factory_gives_fallback_time():
    seen = []
    cancelled = []

    async def handler(req):
        model = json.loads(req.content)['model']
        seen.append(model)
        if model == PRIMARY:
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.append(model)
                raise
        # Consume some of the reserved budget, not an instantaneous response.
        await asyncio.sleep(0.04)
        return httpx.Response(200, json={**BODY, 'model': model})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await provider(client).complete(request())
            assert response.text == 'ok'
            assert response.model == FALLBACK

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY, FALLBACK]
    assert cancelled == [PRIMARY]


def test_primary_budget_also_interrupts_retry_backoff():
    seen = []

    async def handler(req):
        model = json.loads(req.content)['model']
        seen.append(model)
        if model == PRIMARY:
            raise httpx.ReadTimeout('isolated slow primary', request=req)
        return httpx.Response(200, json={**BODY, 'model': model})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await provider(client).complete(request())).model == FALLBACK

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY, FALLBACK]


def test_hung_fallback_still_obeys_total_deadline():
    seen = []
    cancelled = []

    async def handler(req):
        model = json.loads(req.content)['model']
        seen.append(model)
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled.append(model)
            raise
        return httpx.Response(200, json=BODY)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ProviderTransportError) as exc:
                await provider(client).complete(request())
            assert exc.value.reason == 'timeout'

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY, FALLBACK]
    assert cancelled == [PRIMARY, FALLBACK]


@pytest.mark.parametrize('fallback', ['', PRIMARY])
def test_no_usable_fallback_keeps_primary_full_budget(fallback):
    seen = []

    async def handler(req):
        seen.append(json.loads(req.content)['model'])
        await asyncio.sleep(0.24)  # Longer than 2/3 of the 0.3 s total.
        return httpx.Response(200, json=BODY)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await provider(client, fallback=fallback).complete(request())).text == 'ok'

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY]


def test_successful_primary_never_calls_fallback():
    seen = []

    async def handler(req):
        seen.append(json.loads(req.content)['model'])
        return httpx.Response(200, json={**BODY, 'model': PRIMARY})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await provider(client).complete(request())).model == PRIMARY

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY]


def test_caller_cancellation_is_not_reinterpreted_as_primary_failure():
    started = asyncio.Event()
    seen = []

    async def handler(req):
        seen.append(json.loads(req.content)['model'])
        started.set()
        await asyncio.sleep(5)
        return httpx.Response(200, json=BODY)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            job = asyncio.create_task(provider(client).complete(request()))
            await started.wait()
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await job

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY]


def test_fast_primary_failure_leaves_all_remaining_time_for_fallback():
    seen = []

    async def handler(req):
        model = json.loads(req.content)['model']
        seen.append(model)
        if model == PRIMARY:
            return httpx.Response(403, json={'error': 'isolated primary rejection'})
        await asyncio.sleep(0.24)  # More than the reserved last third alone.
        return httpx.Response(200, json={**BODY, 'model': model})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await provider(client).complete(request())).model == FALLBACK

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY, FALLBACK]


def test_primary_setup_time_cannot_shift_its_deadline():
    seen = []

    async def handler(req):
        model = json.loads(req.content)['model']
        seen.append(model)
        if model == PRIMARY:
            await asyncio.sleep(5)
        return httpx.Response(200, json={**BODY, 'model': model})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            instance = provider(client)
            traced = instance._complete_traced

            async def setup_then_trace(req, model, extra_metadata=None, *, deadline=None):
                if model == PRIMARY:
                    await asyncio.sleep(0.15)
                return await traced(req, model, extra_metadata, deadline=deadline)

            instance._complete_traced = setup_then_trace
            assert (await instance.complete(request())).model == FALLBACK

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))
    assert seen == [PRIMARY, FALLBACK]
