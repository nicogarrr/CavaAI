"""Raw request-body capture for request-signature verification.

FastAPI reads (and may discard) the body before solving dependencies — for
multipart/form routes the raw bytes are consumed by the form parser and a
later ``await request.body()`` raises ``RuntimeError("Stream consumed")``.
This pure-ASGI middleware buffers the body once, replays it downstream so
every consumer sees the same bytes, and exposes the raw bytes on
``request.state.raw_body`` for HMAC body-hash verification.
"""

from __future__ import annotations

from typing import Any


class RawBodyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        chunks: list[bytes] = []
        message: dict[str, Any] = await receive()
        chunks.append(message.get("body", b""))
        while message.get("more_body"):
            message = await receive()
            chunks.append(message.get("body", b""))
        raw_body = b"".join(chunks)

        scope.setdefault("state", {})["raw_body"] = raw_body
        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": raw_body, "more_body": False}

        await self.app(scope, replay_receive, send)
