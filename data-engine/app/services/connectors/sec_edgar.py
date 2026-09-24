"""Fundamentales gratuitos de SEC EDGAR (10-K/10-Q). Sin API key: solo User-Agent de contacto.

Idea originada en TauricResearch/TradingAgents
``tradingagents/dataflows/sec_edgar.py`` (Apache-2.0): EDGAR no pide clave,
pero la SEC exige un User-Agent que identifique al llamante con un contacto y
rechaza las peticiones sin el. Implementacion propia para CavaAI: cliente
``httpx`` asincrono (inyectable en tests), tolerante a 429 con backoff
exponencial y respeto a ``Retry-After``, y normalizacion minima de conceptos
us-gaap de 10-K (anual) y 10-Q (trimestral).
"""

from __future__ import annotations

from pathlib import Path

import asyncio
import os
from typing import Any

import httpx

from app.core.config import get_settings

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"

DEFAULT_CONTACT = "contact@example.com"
# Cabecera tipo navegador + contacto: la SEC bloquea User-Agents sin contacto.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (compatible; CavaAI/0.1; +mailto:{contact}) CavaAI Research"
)

ANNUAL_FORMS = {"10-K", "20-F"}
QUARTERLY_FORMS = {"10-Q"}

# Metrica -> tags us-gaap por orden de preferencia (el primero que informa gana;
# nunca se suman tags: un mismo ingreso bajo dos tags se contaria dos veces).
METRIC_CONCEPTS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps_diluted": ("EarningsPerShareDiluted",),
    "total_assets": ("Assets",),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
}


def resolve_user_agent() -> str:
    """User-Agent con contacto: env ``SEC_EDGAR_USER_AGENT`` > settings > defecto."""
    configured = os.getenv("SEC_EDGAR_USER_AGENT", "").strip()
    candidate = configured or get_settings().sec_user_agent.strip() or ""
    if "@" not in candidate:
        candidate = BROWSER_USER_AGENT.format(contact=DEFAULT_CONTACT)
    elif candidate.startswith("CavaAI/") and "Mozilla" not in candidate:
        candidate = BROWSER_USER_AGENT.format(contact=candidate.split()[-1].strip("()"))
    return candidate


def default_headers(user_agent: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": user_agent or resolve_user_agent(),
        "Accept": "application/json, text/html, */*",
        "Accept-Encoding": "gzip, deflate",
    }


def _pad_cik(cik: str | int) -> str:
    return str(cik).strip().zfill(10)


def _snapshot_path_for(url: str) -> Path | None:
    """Ruta del snapshot local para una URL EDGAR, o None si no aplica.

    Layout: $SEC_SNAPSHOT_DIR/company_tickers.json,
    $SEC_SNAPSHOT_DIR/companyfacts/CIK##########.json y
    $SEC_SNAPSHOT_DIR/submissions/CIK##########.json (mismo formato JSON
    que la API oficial, con fetched_at real en manifest.json).
    """
    import re

    from app.core.config import get_settings

    base = get_settings().sec_snapshot_dir
    if not base:
        return None
    root = Path(base)
    if url == TICKER_MAP_URL:
        return root / "company_tickers.json"
    match = re.search(r"(?:companyfacts|submissions)/CIK(\d{10})\.json$", url)
    if match:
        kind = "companyfacts" if "companyfacts" in url else "submissions"
        return root / kind / f"CIK{match.group(1)}.json"
    return None


def _read_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    import json

    data = json.loads(path.read_text())
    return data if isinstance(data, dict) else None


async def _get_json(
    url: str,
    client: httpx.AsyncClient | None = None,
    *,
    max_retries: int = 4,
    base_delay: float = 1.0,
    user_agent: str | None = None,
) -> dict[str, Any]:
    """GET JSON tolerante a 429: backoff exponencial + cabecera ``Retry-After``.

    Si hay snapshot local para la URL (SEC_SNAPSHOT_DIR), se usa en vez de la
    red: la SEC bloquea las IPs de datacenter y el dato es igual de oficial.
    """
    snapshot = _read_snapshot(_snapshot_path_for(url))
    if snapshot is not None:
        return snapshot
    headers = default_headers(user_agent)
    delay = base_delay
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if client is not None:
            response = await client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient(
                timeout=30, headers=headers, follow_redirects=True
            ) as owned:
                response = await owned.get(url)
        if response.status_code == 429 and attempt < max_retries:
            retry_after = response.headers.get("retry-after")
            try:
                wait = float(retry_after) if retry_after else delay
            except (TypeError, ValueError):
                wait = delay
            await asyncio.sleep(max(0.0, min(wait, 60.0)))
            delay *= 2
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"SEC EDGAR request failed ({response.status_code} {url})"
            ) from exc
        last_error = None
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"SEC EDGAR returned non-object JSON ({url})")
        return data
    raise RuntimeError(
        f"SEC EDGAR rate-limited (429 {url}) after {max_retries} retries"
    ) from last_error


def _manifest_cik(ticker: str) -> str | None:
    """CIK desde el manifest del snapshot (evita el company_tickers de 2MB)."""
    import json

    from app.core.config import get_settings

    base = get_settings().sec_snapshot_dir
    if not base:
        return None
    manifest = Path(base) / "manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text())
    tickers = data.get("tickers", {}) if isinstance(data, dict) else {}
    cik = tickers.get(ticker.strip().upper())
    return _pad_cik(cik) if cik else None


async def cik_for_ticker(
    ticker: str, client: httpx.AsyncClient | None = None
) -> str | None:
    """CIK a 10 digitos para un ticker US, o None si no es filer EDGAR."""
    from_manifest = _manifest_cik(ticker)
    if from_manifest is not None:
        return from_manifest
    table = await _get_json(TICKER_MAP_URL, client)
    wanted = ticker.strip().upper()
    for entry in table.values():
        if isinstance(entry, dict) and str(entry.get("ticker", "")).upper() == wanted:
            return _pad_cik(entry["cik_str"])
    return None


async def company_facts(
    cik: str | int, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """Hechos XBRL (companyfacts) tal como fueron fileados, sin normalizar."""
    return await _get_json(COMPANYFACTS_URL.format(cik=_pad_cik(cik)), client)


async def recent_filings(
    cik: str | int,
    forms: tuple[str, ...] = ("10-K", "10-Q"),
    limit: int = 10,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Filings recientes filtrados por formulario (por defecto 10-K/10-Q)."""
    payload = await _get_json(SUBMISSIONS_URL.format(cik=_pad_cik(cik)), client)
    recent = payload.get("filings", {}).get("recent", {})
    allowed = {form.upper() for form in forms}
    cik_number = str(int(str(cik).strip()))
    items: list[dict[str, Any]] = []
    accessions = recent.get("accessionNumber", [])
    for index, accession in enumerate(accessions):
        form = str(recent.get("form", [None])[index] if index < len(recent.get("form", [])) else None or "")
        if form.upper() not in allowed:
            continue

        def _col(name: str) -> Any:
            values = recent.get(name, [])
            return values[index] if index < len(values) else None

        primary = _col("primaryDocument")
        accession_nodash = str(accession).replace("-", "")
        index_url = f"{ARCHIVES_URL}/{cik_number}/{accession_nodash}/"
        items.append(
            {
                "form": form,
                "accession_number": accession,
                "filing_date": _col("filingDate"),
                "report_date": _col("reportDate"),
                "primary_document": primary,
                "index_url": index_url,
                "document_url": f"{index_url}{primary}" if primary else index_url,
            }
        )
        if len(items) >= limit:
            break
    return items


def extract_metric_values(
    us_gaap: dict[str, Any],
    tags: tuple[str, ...],
    *,
    forms: set[str] | None = None,
    unit: str = "USD",
) -> dict[str, Any] | None:
    """Ultimo valor fileado para una metrica.

    Los alias de tag se fusionan antes de elegir (no "gana el primero que
    informe"): los filers migran de tag y el antiguo queda congelado en el
    pasado; el valor actual vive en el tag nuevo.
    """
    wanted_forms = forms or (ANNUAL_FORMS | QUARTERLY_FORMS)
    candidates: list[tuple[str, dict]] = []
    for tag in tags:
        entries = ((us_gaap.get(tag) or {}).get("units", {}) or {}).get(unit, [])
        candidates.extend(
            (tag, e)
            for e in entries
            if isinstance(e, dict)
            and str(e.get("form", "")).upper() in wanted_forms
            and e.get("val") is not None
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda te: (str(te[1].get("filed", "")), str(te[1].get("end", "")))
    )
    tag, latest = candidates[-1]
    return {
        "concept": tag,
        "value": latest["val"],
        "unit": unit,
        "end": latest.get("end"),
        "filed": latest.get("filed"),
        "form": latest.get("form"),
        "periods": len({str(e.get("end")) for _, e in candidates}),
    }


async def get_fundamentals(
    ticker: str,
    cik: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Snapshot de fundamentales gratuitos: metricas + ultimos 10-K/10-Q."""
    resolved_cik = cik or await cik_for_ticker(ticker, client)
    if not resolved_cik:
        return {
            "status": "unavailable",
            "ticker": ticker.upper(),
            "reason": "not a US SEC filer",
        }
    facts = await company_facts(resolved_cik, client)
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    metrics: dict[str, Any] = {}
    for metric, tags in METRIC_CONCEPTS.items():
        found = extract_metric_values(us_gaap, tags)
        if found:
            metrics[metric] = found
    return {
        "status": "ok",
        "ticker": ticker.upper(),
        "cik": _pad_cik(resolved_cik),
        "company_name": facts.get("entityName"),
        "metrics": metrics,
        "recent_filings": await recent_filings(resolved_cik, client=client),
    }

# Alias publicos para el cliente async (connectors/sec.py).
manifest_cik = _manifest_cik


def read_snapshot_for(url: str) -> dict[str, Any] | None:
    """Snapshot local para una URL EDGAR, o None si no hay fichero."""
    return _read_snapshot(_snapshot_path_for(url))
