"""OpenFIGI v3 identifier mapping without an API key.

Return all matches rather than guessing a listing when an ISIN maps to
multiple venues. Callers must disambiguate exchange/currency before use.
"""

from __future__ import annotations

from typing import Any

import httpx


class OpenFIGIClient:
    name = "openfigi"
    base_url = "https://api.openfigi.com/v3/mapping"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    def configured(self) -> bool:
        return True

    async def map_identifier(
        self, value: str, *, id_type: str = "ID_ISIN", exch_code: str | None = None
    ) -> dict[str, Any]:
        """One mapping job. Status `ambiguous` is deliberately not a ticker pick."""
        if id_type not in {"ID_ISIN", "ID_BB_GLOBAL"}:
            raise ValueError("Only ISIN and FIGI mappings are supported")
        value = value.strip().upper()
        if not value or len(value) > 40:
            raise ValueError("Invalid identifier")
        job = {"idType": id_type, "idValue": value}
        if exch_code:
            job["exchCode"] = exch_code.strip().upper()
        if self.client is None:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.base_url, json=[job])
        else:
            response = await self.client.post(self.base_url, json=[job])
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise RuntimeError("OpenFIGI returned an invalid mapping response")
        result = payload[0]
        if result.get("error"):
            return {"status": "error", "identifier": value, "matches": [], "error": str(result["error"]), "source": self.name, "source_url": self.base_url}
        matches = result.get("data") or []
        if not isinstance(matches, list) or any(not isinstance(row, dict) for row in matches):
            raise RuntimeError("OpenFIGI returned invalid mapping matches")
        clean = [
            {key: row.get(key) for key in ("figi", "compositeFIGI", "shareClassFIGI", "ticker", "name", "exchCode", "marketSector", "securityType", "securityType2")}
            for row in matches if row.get("figi")
        ]
        return {
            "status": "unavailable" if not clean else "matched" if len(clean) == 1 else "ambiguous",
            "identifier": value,
            "matches": clean,
            "source": self.name,
            "source_url": self.base_url,
        }
