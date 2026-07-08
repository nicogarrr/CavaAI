from xml.etree import ElementTree

import httpx

from app.core.config import get_settings


class IBKRFlexClient:
    send_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest"
    get_url = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"

    def __init__(self) -> None:
        self.settings = get_settings()

    def configured(self) -> bool:
        return bool(self.settings.ibkr_flex_token and self.settings.ibkr_flex_query_id)

    async def request_statement(self) -> str:
        if not self.configured():
            raise RuntimeError("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID are not configured")
        params = {
            "t": self.settings.ibkr_flex_token,
            "q": self.settings.ibkr_flex_query_id,
            "v": "3",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(self.send_url, params=params)
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
            status = root.findtext(".//Status")
            if status != "Success":
                raise RuntimeError(f"IBKR Flex request failed: {response.text[:300]}")
            reference_code = root.findtext(".//ReferenceCode")
            if not reference_code:
                raise RuntimeError("IBKR Flex did not return a ReferenceCode")
            return reference_code

    async def fetch_statement(self, reference_code: str) -> str:
        if not self.configured():
            raise RuntimeError("IBKR_FLEX_TOKEN and IBKR_FLEX_QUERY_ID are not configured")
        params = {"t": self.settings.ibkr_flex_token, "q": reference_code, "v": "3"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(self.get_url, params=params)
            response.raise_for_status()
            return response.text

    async def fetch_latest_xml(self) -> str:
        reference_code = await self.request_statement()
        return await self.fetch_statement(reference_code)

