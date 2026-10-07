import asyncio

import httpx
import pytest

from app.llm.adapters import OpenAICompatibleProvider
from app.llm.errors import LLMError


@pytest.mark.parametrize(("kind","expected"), [(httpx.ReadTimeout,"read_timeout"),(httpx.ConnectTimeout,"connect_timeout"),(httpx.ConnectError,"connect_error"),(httpx.RemoteProtocolError,"protocol_error")])
def test_transport_failure_has_safe_class_and_attempt_count(kind,expected):
    async def run():
        calls=0
        def handler(request):
            nonlocal calls
            calls+=1
            raise kind("secret-key-abc private-url prompt text", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            p=OpenAICompatibleProvider(api_key="secret-key-abc",base_url="https://private-url.test/v1",default_model="m",client=client,max_retries=1)
            with pytest.raises(LLMError) as err:
                await p._post_json("https://private-url.test/v1/chat/completions",headers={"Authorization":"Bearer secret-key-abc"},payload={"private":"prompt text"})
            assert err.value.reason==expected
            assert err.value.attempts==calls==2
            assert "secret-key-abc" not in str(err.value)
            assert "private-url" not in str(err.value)
            assert "prompt text" not in str(err.value)
    asyncio.run(run())
