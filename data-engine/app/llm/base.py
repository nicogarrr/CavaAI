from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Any, Mapping

import httpx

from app.llm.contracts import LLMRequest, LLMResponse, ResponseFormat
from app.llm.errors import LLMError, ProviderHTTPError, ProviderResponseError
from app.llm.json import parse_json_response
from app.llm.routing import TaskModelRouter


class LLMProvider(ABC):
    name: str

    def __init__(
        self,
        *,
        model_router: TaskModelRouter,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.model_router = model_router
        self._client = client
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    async def generate_json(
        self,
        request: LLMRequest,
        *,
        schema: Mapping[str, Any] | None = None,
        schema_name: str = "response",
    ) -> Any:
        response_format = (
            ResponseFormat.json_schema(schema, name=schema_name)
            if schema is not None
            else ResponseFormat.json_object()
        )
        response = await self.complete(replace(request, response_format=response_format))
        return parse_json_response(response.text)

    async def _post_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._send(url, headers=headers, payload=payload)
            except httpx.HTTPError:
                if attempt >= self._max_retries:
                    raise LLMError(f"{self.name} request failed") from None
                await asyncio.sleep(0.25 * (2**attempt))
                continue

            if response.status_code < 400:
                return response
            if response.status_code not in {408, 409, 429} and response.status_code < 500:
                raise ProviderHTTPError(self.name, response.status_code)
            if attempt >= self._max_retries:
                raise ProviderHTTPError(self.name, response.status_code)
            await asyncio.sleep(0.25 * (2**attempt))

        raise LLMError(f"{self.name} request failed")

    async def _send(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        if self._client is not None:
            return await self._client.post(
                url,
                headers=dict(headers),
                json=dict(payload),
                timeout=self._timeout,
            )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, headers=dict(headers), json=dict(payload))

    def _response_json(self, response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            raise ProviderResponseError(f"{self.name} returned a non-JSON response") from None
        if not isinstance(payload, dict):
            raise ProviderResponseError(f"{self.name} returned an invalid response envelope")
        return payload
