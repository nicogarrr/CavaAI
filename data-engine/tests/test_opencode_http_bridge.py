"""Offline bridge transport canaries: no model, credentials or production traffic."""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location("oc_bridge", Path(__file__).parents[1] / "bridge/opencode_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def run_with_responses(responses):
    calls = []
    def request(method, path, body=None, **kwargs):
        calls.append((method, path, body, kwargs))
        if path == "/session": return {"id": "synthetic"}
        if path.endswith("prompt_async"): return None
        if path.endswith("abort") or method == "DELETE": return None
        if path == "/session/status": return responses.get("status", {})
        return responses["messages"].pop(0)
    return calls, request

def test_async_empty_response_and_latest_poll_only():
    pending = [{"info": {"role": "assistant"}, "parts": [{"type": "text", "text": "part"}]}]
    done = [{"info": {"role": "assistant", "finish": "stop"}, "parts": [{"type": "text", "text": "whole"}]}]
    calls, request = run_with_responses({"messages": [pending, done]})
    with patch.object(bridge, "serve_req", request), patch.object(bridge.time, "sleep"):
        assert bridge.complete("fixture-free", [{"role": "user", "content": "test"}]) == "whole"
    assert calls[0][2] == {"title": "CavaAI chat"}
    assert any(path.endswith("prompt_async") for _, path, _, _ in calls)
    assert calls[-2][1].endswith("abort") and calls[-1][0] == "DELETE"

def test_valid_primary_at_44_seconds_is_not_aborted():
    done = [{"info": {"role": "assistant", "finish": "stop"}, "parts": [{"type": "text", "text": "valid primary"}]}]
    calls, request = run_with_responses({"messages": [done]})
    with patch.object(bridge, "serve_req", request), patch.object(bridge.time, "monotonic", side_effect=[0, 44]):
        assert bridge.complete("fixture-free", [{"role": "user", "content": "test"}]) == "valid primary"
    assert calls[-1][0] == "DELETE"

def test_provider_error_aborts_and_cleans_up():
    calls, request = run_with_responses({"messages": [[{"info": {"role": "assistant", "error": {"name": "APIError"}}, "parts": []}]]})
    with patch.object(bridge, "serve_req", request):
        with pytest.raises(RuntimeError, match="serve error"): bridge.complete("fixture-free", [{"role": "user", "content": "test"}])
    assert calls[-2][1].endswith("abort") and calls[-1][0] == "DELETE"


def test_deadline_cancels_without_synchronous_message_call():
    calls, request = run_with_responses({"messages": []})
    with patch.object(bridge, "serve_req", request), patch.object(bridge.time, "monotonic", side_effect=[0, 151]):
        with pytest.raises(TimeoutError): bridge.complete("fixture-free", [{"role": "user", "content": "test"}])
    assert calls[-2][1].endswith("abort") and calls[-1][0] == "DELETE"
    assert not any(path.endswith("/message") and method == "POST" for method, path, _, _ in calls)
