import asyncio
from xml.etree import ElementTree

import httpx

from app.core.config import get_settings


class IBKRFlexError(RuntimeError):
    """Error del Flex Web Service sin URL ni parametros: el token viaja en la query string."""


# Codigos de IBKR que significan "vuelve a pedirlo en unos segundos".
_RETRY_CODES = {"1001", "1004", "1005", "1006", "1007", "1008", "1009", "1019", "1021"}


class IBKRFlexClient:
    send_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
    get_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
    poll_attempts = 6
    poll_delay_seconds = 10.0

    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.ibkr_flex_token and self.settings.ibkr_flex_query_id)

    def _require_config(self) -> None:
        if not self.configured():
            raise RuntimeError("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID are not configured")

    async def _get(self, url: str, params: dict[str, str], timeout: float) -> str:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.text
        except httpx.HTTPStatusError as exc:
            # str(exc) lleva la URL completa, token incluido.
            raise IBKRFlexError(f"IBKR Flex HTTP {exc.response.status_code}") from None
        except httpx.HTTPError as exc:
            raise IBKRFlexError(f"IBKR Flex network error: {type(exc).__name__}") from None

    @staticmethod
    def _status(text: str) -> tuple[str | None, str | None, str | None]:
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            return None, None, None
        return root.findtext(".//Status"), root.findtext(".//ErrorCode"), root.findtext(".//ErrorMessage")

    async def request_statement(self) -> str:
        self._require_config()
        params = {
            "t": self.settings.ibkr_flex_token,
            "q": self.settings.ibkr_flex_query_id,
            "v": "3",
        }
        text = await self._get(self.send_url, params, 30)
        status, code, message = self._status(text)
        if status != "Success":
            raise IBKRFlexError(f"IBKR Flex request failed (code {code or 'n/d'}): {(message or '')[:200]}")
        root = ElementTree.fromstring(text)
        reference_code = root.findtext(".//ReferenceCode")
        if not reference_code:
            raise IBKRFlexError("IBKR Flex did not return a ReferenceCode")
        return reference_code

    async def fetch_statement(self, reference_code: str) -> str:
        self._require_config()
        params = {"t": self.settings.ibkr_flex_token, "q": reference_code, "v": "3"}
        last = "sin respuesta"
        for attempt in range(self.poll_attempts):
            text = await self._get(self.get_url, params, 60)
            status, code, message = self._status(text)
            if status is None:
                # El extracto real no trae <Status>: es FlexQueryResponse.
                return text
            last = f"code {code or 'n/d'}: {(message or '')[:120]}"
            if code not in _RETRY_CODES:
                raise IBKRFlexError(f"IBKR Flex statement failed ({last})")
            if attempt + 1 < self.poll_attempts:
                await asyncio.sleep(self.poll_delay_seconds)
        raise IBKRFlexError(f"IBKR Flex statement not ready ({last})")

    async def fetch_latest_xml(self) -> str:
        reference_code = await self.request_statement()
        return await self.fetch_statement(reference_code)
