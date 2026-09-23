"""Yahoo Finance chart API (sin key): cotizaciones y eventos de dividendo/split.

Sustituto gratuito del proveedor FMP (eliminado: su key está muerta) para
precios y acciones corporativas. La chart API exige User-Agent de navegador
y no requiere autenticación. Los errores se propagan como excepciones para
que el caller pueda pasar al siguiente proveedor de la cadena.
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class YahooFinanceClient:
    name = "yahoo"
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    def configured(self) -> bool:
        # La chart API de Yahoo no necesita key: siempre disponible.
        return True

    async def _chart(self, ticker: str, *, events: bool = False) -> dict[str, Any]:
        params: dict[str, Any] = {"range": "max", "interval": "1d"}
        if events:
            params = {
                "period1": 0,
                "period2": int(time.time()) + 86400,
                "interval": "1d",
                "events": "div|split",
            }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/{ticker.upper()}", params=params, headers=self.headers
            )
            response.raise_for_status()
            payload = response.json()
        result = payload.get("chart", {}).get("result") if isinstance(payload, dict) else None
        if not result:
            raise RuntimeError("Yahoo returned an empty chart")
        return result[0]

    async def quote(self, ticker: str) -> dict[str, Any]:
        """Meta de cotización (regularMarketPrice, previousClose, ...)."""
        node = await self._chart(ticker)
        meta = node.get("meta") or {}
        if not isinstance(meta, dict) or not meta.get("regularMarketPrice"):
            raise RuntimeError("Yahoo returned no market price")
        return meta

    async def dividends(self, ticker: str) -> list[dict[str, Any]]:
        """Eventos de dividendo crudos ({date: epoch, amount, dividends})."""
        node = await self._chart(ticker, events=True)
        events = node.get("events") or {}
        rows = list((events.get("dividends") or {}).values())
        return [row for row in rows if isinstance(row, dict)]

    async def splits(self, ticker: str) -> list[dict[str, Any]]:
        """Eventos de split crudos ({date: epoch, numerator, denominator, splitRatio})."""
        node = await self._chart(ticker, events=True)
        events = node.get("events") or {}
        rows = list((events.get("splits") or {}).values())
        return [row for row in rows if isinstance(row, dict)]
