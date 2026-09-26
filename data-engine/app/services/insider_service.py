"""Senales insider a partir de Form 4 (SEC EDGAR, gratis).

Senales (codigo P = compra en mercado abierto O privada; el XML no
siempre lo distingue, asi que los textos nunca afirman "mercado abierto"):
- cluster_buy: >=3 insiders distintos comprando (codigo P) en 30 dias.
- c_suite_buy: el CEO/CFO compra (codigo P).
- big_buy: una compra (codigo P) supera 1M USD.

Enganche minimo con Telegram (notification_service): `maybe_notify_insider_buy`
solo actua si INSIDER_ALERTS_ENABLED=true y nunca rompe el flujo (todo
envuelto en try/except -> devuelve {"status": "skipped", ...}).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import get_settings
from app.services.connectors import form4 as form4_connector
from app.services.provenance import Coverage, SourceKind, provenance

CLUSTER_MIN_INSIDERS = 3
CLUSTER_WINDOW_DAYS = 30
BIG_BUY_THRESHOLD_USD = 1_000_000.0

#: Timeout por fetch de filing XML (segundos). El conector usa 30 fijos;
#: aquí creamos cliente propio acotado cuando el llamante no inyecta uno.
FILING_FETCH_TIMEOUT_SECONDS = 15.0
#: TTL del XML por accession (los filings SEC son inmutables; la caché solo
#: evita re-descargas en re-evaluaciones).
FILING_XML_CACHE_TTL_SECONDS = 3600

_xml_cache: dict[str, tuple[float, str]] = {}
_xml_cache_fetched_at: dict[str, str] = {}


def _cached_filing_xml(filing: dict, client=None) -> tuple[str, str | None]:
    """XML del filing con caché TTL por accession + timeout acotado.

    Devuelve ``(xml, cached_fetched_at)``. ``cached_fetched_at`` es None en
    descarga fresca. Nunca lanza por la caché: ante cualquier duda se
    descarga de nuevo.
    """
    accession = str(filing.get("accession_number") or filing.get("document_url") or "")
    now = time.time()
    try:
        expires, xml_text = _xml_cache.get(accession, (0.0, ""))
        if xml_text and expires > now:
            return xml_text, _xml_cache_fetched_at.get(accession)
    except Exception:  # noqa: BLE001 — la caché nunca rompe el fetch
        pass
    owned_client = None
    try:
        if client is None:
            import httpx as _httpx

            owned_client = _httpx.Client(
                timeout=FILING_FETCH_TIMEOUT_SECONDS,
                headers=form4_connector.default_headers(),
            )
            xml_text = form4_connector.fetch_filing_xml(
                filing["document_url"], client=owned_client
            )
        else:
            xml_text = form4_connector.fetch_filing_xml(
                filing["document_url"], client=client
            )
    finally:
        if owned_client is not None:
            owned_client.close()
    try:
        _xml_cache[accession] = (now + FILING_XML_CACHE_TTL_SECONDS, xml_text)
        _xml_cache_fetched_at[accession] = datetime.now(UTC).isoformat()
    except Exception:  # noqa: BLE001 — best-effort
        pass
    return xml_text, None


def clear_filing_xml_cache() -> None:
    """Helper de tests: vacía la caché de filings."""
    _xml_cache.clear()
    _xml_cache_fetched_at.clear()



def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    """Parse a numeric field that may arrive as str/None/garbage from Form 4 XML."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_c_suite(tx: dict) -> bool:
    return _is_ceo(tx) or _is_cfo(tx)


# Matched against the WHOLE title as words, never as a substring: "president"
# is a substring of "Vice President, Human Resources", so a VP of HR was
# reported as the CEO buying, and the alert named the wrong person.
_CEO_TITLE_PATTERNS = (
    r"\bchief\s+executive(\s+officer)?\b",
    r"\bceo\b",
    r"\bpresident\s+and\s+chief\s+executive\b",
    r"\bpresident\s*,?\s+chief\s+executive\b",
    r"\bchairman\s+and\s+ceo\b",
    r"\bchair\s+and\s+ceo\b",
)
_CFO_TITLE_PATTERNS = (
    r"\bchief\s+financial(\s+officer)?\b",
    r"\bcfo\b",
    r"\bvice\s+president\s+and\s+cfo\b",
    r"\bpresident\s*,?\s+chief\s+financial\s+officer\b",
)
# A title that marks the holder as NOT the top officer, and that can appear
# ALONGSIDE a real top-officer marker ("Vice President and CFO"), so the veto
# below only applies when no explicit marker is present.
_NOT_TOP_OFFICER = re.compile(r"\b(vice\s+president|vp|deputy|assistant|associate)\b")
# An explicit statement that this person IS the top officer.
_TOP_OFFICER_MARKER = re.compile(
    r"\b(chief|ceo|cfo|coo|cio|cpres|chairman|chair)\b"
)


def _title_matches(tx: dict, patterns: tuple[str, ...]) -> bool:
    title = str(tx.get("officer_title") or "").lower()
    role = str(tx.get("role") or "").lower()
    if not title and not role:
        return False
    # Only a DIRECTOR/OFFICER can be C-suite by title; a plain shareholder is
    # not promoted by the word "president" appearing anywhere.
    if role and "director" not in role and "officer" not in role:
        return False
    haystack = f"{title} {role}"
    if not any(re.search(pattern, haystack) for pattern in patterns):
        return False
    # "Vice President, Finance" also contains "president", so without this the
    # substring match would promote a VP. But "Vice President and CFO" names
    # the office explicitly and must survive.
    if _NOT_TOP_OFFICER.search(title) and not _TOP_OFFICER_MARKER.search(title):
        return False
    return True


def _is_ceo(tx: dict) -> bool:
    return _title_matches(tx, _CEO_TITLE_PATTERNS)


def _is_cfo(tx: dict) -> bool:
    return _title_matches(tx, _CFO_TITLE_PATTERNS)


def open_market_buys(transactions: list[dict]) -> list[dict]:
    """Compras por codigo P + adquirida (mercado abierto O privadas)."""
    return [tx for tx in transactions if form4_connector.is_open_market_buy(tx)]


def detect_signals(transactions: list[dict]) -> list[dict]:
    """Detecta cluster_buy, c_suite_buy y big_buy sobre transacciones Form 4."""
    buys = open_market_buys(transactions)
    signals: list[dict] = []

    for tx in buys:
        amount = _to_float(tx.get("value"))
        if amount is not None and amount > BIG_BUY_THRESHOLD_USD:
            signals.append(
                {
                    "signal": "big_buy",
                    "ticker": tx.get("ticker"),
                    "insider": tx.get("insider"),
                    "role": tx.get("role"),
                    "date": tx.get("date"),
                    "shares": tx.get("shares"),
                    "price": tx.get("price"),
                    "value": amount,
                    "source_url": tx.get("source_url"),
                    "form": tx.get("form"),
                    "multi_reporter": tx.get("multi_reporter", False),
                    "detail": (
                        f"{tx.get('insider')} compra ${amount:,.0f} "
                        f"({tx.get('shares')} acc. @ ${tx.get('price')})"
                    ),
                }
            )
        if _is_c_suite(tx):
            who = "CEO" if _is_ceo(tx) else ("CFO" if _is_cfo(tx) else "C-suite")
            signals.append(
                {
                    "signal": "c_suite_buy",
                    "ticker": tx.get("ticker"),
                    "insider": tx.get("insider"),
                    "role": tx.get("role"),
                    "officer_title": tx.get("officer_title"),
                    "date": tx.get("date"),
                    "shares": tx.get("shares"),
                    "price": tx.get("price"),
                    "value": amount,
                    "source_url": tx.get("source_url"),
                    "form": tx.get("form"),
                    "multi_reporter": tx.get("multi_reporter", False),
                    "detail": f"{who} {tx.get('insider')} compra (código P: mercado abierto o privado)",
                }
            )

    # Cluster: por ticker, >=3 insiders distintos comprando en 30 dias.
    by_ticker: dict[str, list[dict]] = {}
    for tx in buys:
        if tx.get("ticker"):
            by_ticker.setdefault(str(tx["ticker"]).upper(), []).append(tx)
    for ticker, items in by_ticker.items():
        dated = [( _parse_date(tx.get("date")), tx) for tx in items]
        dated = [(d, tx) for d, tx in dated if d is not None]
        dated.sort(key=lambda pair: pair[0])
        if len({tx.get("insider_cik") or tx.get("insider") for _, tx in dated}) < CLUSTER_MIN_INSIDERS:
            continue
        found = False
        for start in range(len(dated)):
            window = [
                tx for d, tx in dated
                if 0 <= (d - dated[start][0]).days <= CLUSTER_WINDOW_DAYS
            ]
            insiders = {tx.get("insider_cik") or tx.get("insider") for tx in window}
            if len(insiders) >= CLUSTER_MIN_INSIDERS:
                total = sum(
                    value
                    for value in (_to_float(tx.get("value")) for tx in window)
                    if value is not None
                )
                signals.append(
                    {
                        "signal": "cluster_buy",
                        "ticker": ticker,
                        "insiders": sorted(insiders),
                        "insider_count": len(insiders),
                        "window_days": CLUSTER_WINDOW_DAYS,
                        "window_start": dated[start][0].isoformat(),
                        "buy_count": len(window),
                        "total_value": total,
                        "detail": (
                            f"{len(insiders)} insiders compran {ticker} "
                            f"en {CLUSTER_WINDOW_DAYS} dias (${total:,.0f})"
                        ),
                    }
                )
                found = True
                break
        if found:
            continue

    return signals


def get_signals_for_ticker(
    ticker: str,
    *,
    cik: str | None = None,
    limit: int = 20,
    client=None,
    fetcher: Callable[..., list[dict]] | None = None,
    db=None,
    tenant_id: int | None = None,
) -> dict:
    """Pipeline ticker -> filings Form 4 -> parse XML -> senales. Best-effort.

    `fetcher(accession...)` es inyectable para tests hermeticos. Cualquier
    fallo de red/parse degrada a status != ok con signals=[] (nunca excepcion).
    """
    wanted = ticker.strip().upper()
    try:
        resolved_cik = cik or _cik_for_ticker(wanted, client)
        if not resolved_cik:
            return {"ticker": wanted, "status": "unavailable",
                    "reason": "not a US SEC filer", "signals": []}
        filings = form4_connector.recent_form4_filings(
            resolved_cik, limit=limit, client=client
        )
        transactions: list[dict] = []
        errors: list[str] = []
        for filing in filings[:limit]:
            try:
                if fetcher is not None:
                    xml_text = fetcher(filing)
                else:
                    xml_text, _cached_at = _cached_filing_xml(filing, client=client)
                parsed = form4_connector.parse_form4_xml(xml_text)
                if db is not None:
                    # Persistencia durable idempotente (PR-2). Nunca rompe la lectura.
                    try:
                        from app.services import insider_persistence

                        insider_persistence.persist_filing(
                            db, filing, parsed, xml_text=xml_text, tenant_id=tenant_id
                        )
                    except Exception as persist_exc:  # noqa: BLE001
                        errors.append(
                            f"{filing.get('accession_number')}: persist {type(persist_exc).__name__}"
                        )
                for tx in parsed.get("transactions", []):
                    tx.setdefault("ticker", wanted)
                    tx["accession_number"] = filing.get("accession_number")
                    tx["filing_date"] = filing.get("filing_date")
                    tx["source_url"] = filing.get("document_url")
                    tx["form"] = filing.get("form")
                    if not tx.get("date"):
                        tx["date"] = filing.get("filing_date")
                transactions.extend(parsed.get("transactions", []))
            except Exception as exc:  # noqa: BLE001 — best-effort por filing
                errors.append(f"{filing.get('accession_number')}: {type(exc).__name__}")
        signals = detect_signals(transactions)
        parse_error_count = len(errors)
        scanned = len(filings[:limit])
        parsed_ok = scanned - parse_error_count
        # `status` is what the endpoint's consumers read, and it was hardcoded
        # to "ok": with 20 filings all failing to fetch, the response said "ok"
        # with `signals: []` and `buy_count: 0`, which reads as "no insider
        # activity" when the truth is "nothing could be read". The user then
        # skips a company on a false all-clear.
        if parse_error_count and parsed_ok == 0:
            status = "degraded"
        elif parse_error_count:
            status = "partial"
        else:
            status = "ok"
        result: dict = {
            "ticker": wanted,
            "cik": resolved_cik,
            "status": status,
            "filings_scanned": scanned,
            "filings_parsed": parsed_ok,
            "filings_failed": parse_error_count,
            "coverage_ratio": (parsed_ok / scanned) if scanned else None,
            "buy_count": len(open_market_buys(transactions)),
            "signals": signals,
            "parse_error_count": parse_error_count,
            "fetched_at": datetime.now(UTC).isoformat(),
            "provenance": provenance(
                "SEC EDGAR",
                SourceKind.OFFICIAL,
                source_url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={resolved_cik}&type=4",
                coverage=Coverage.PARTIAL if errors else Coverage.OK,
                note=(
                    "Form 4 XML; codigo P = mercado abierto o privado. "
                    f"{parse_error_count} filing(s) con error de red/parse de "
                    f"{len(filings[:limit])} escaneados."
                ),
            ),
        }
        if errors:
            result["filing_errors"] = errors
        return result
    except Exception as exc:  # noqa: BLE001 — el endpoint nunca debe romper
        return {"ticker": wanted, "status": "degraded",
                "reason": f"{type(exc).__name__}: {exc}", "signals": []}


# company_tickers.json son ~2 MB y se descarga una vez por ticker resuelto.
# resolve_ciks lo llama en bucle sobre la watchlist, asi que una watchlist de 40
# tickers son 40 descargas de 2 MB a sec.gov en una pasada: ademas de lento, es
# exactamente el patron que hace que la SEC limite o banee la IP de salida
# (fair-access). El mapeo se cachea por proceso; solo se invalida al reiniciar
# el worker, y para CIK de emisores es un dato estable.
_CIK_MAP_CACHE: dict[str, str] | None = None
_CIK_MAP_TTL_SECONDS = 6 * 60 * 60
_CIK_MAP_LOADED_AT: float = 0.0


def _load_cik_map(client=None) -> dict[str, str]:
    """ticker en MAYUSCULAS -> CIK de 10 digitos, cacheado por proceso."""
    global _CIK_MAP_CACHE, _CIK_MAP_LOADED_AT
    import time

    now = time.monotonic()
    if (
        _CIK_MAP_CACHE is not None
        and now - _CIK_MAP_LOADED_AT < _CIK_MAP_TTL_SECONDS
    ):
        return _CIK_MAP_CACHE

    import httpx as _httpx

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = form4_connector.default_headers()
    if client is not None:
        response = client.get(url, headers=headers)
    else:
        with _httpx.Client(timeout=30, headers=headers) as owned:
            response = owned.get(url)
    response.raise_for_status()

    mapping: dict[str, str] = {}
    for entry in response.json().values():
        if isinstance(entry, dict):
            symbol = str(entry.get("ticker", "")).upper()
            cik = entry.get("cik_str")
            if symbol and cik is not None:
                mapping.setdefault(symbol, str(cik).zfill(10))
    _CIK_MAP_CACHE = mapping
    _CIK_MAP_LOADED_AT = now
    return mapping


def _cik_for_ticker(ticker: str, client=None) -> str | None:
    """Resuelve el CIK via company_tickers.json (inyectable en tests)."""
    return _load_cik_map(client=client).get(ticker.strip().upper())


# ---------------- Enganche minimo Telegram (nunca rompe) ----------------


def insider_buy_alert_text(ticker: str, signals: list[dict]) -> str:
    buys = [s for s in signals if s.get("signal") in {"cluster_buy", "c_suite_buy", "big_buy"}]
    lines = [f"Insider buy — {ticker.upper()}: {len(buys)} señal(es)"]
    for sig in buys[:5]:
        lines.append(f"• [{sig['signal']}] {sig.get('detail', '')}")
    return "\n".join(lines)[:4000]


def maybe_notify_insider_buy(
    ticker: str,
    signals: list[dict],
    *,
    notifier: Callable[[dict], dict] | None = None,
) -> dict:
    """Alerta Telegram 'insider buy' detras de INSIDER_ALERTS_ENABLED. Nunca lanza.

    Sin notifier inyectado usa NotificationService._dispatch_telegram con un
    payload minimo (sin DB). Si Telegram no esta configurado o el flag esta
    apagado -> {"status": "skipped", ...}.
    """
    try:
        settings = get_settings()
        if not getattr(settings, "insider_alerts_enabled", False):
            return {"status": "skipped", "reason": "insider alerts disabled"}
        buys = [s for s in signals if s.get("signal") in {"cluster_buy", "c_suite_buy", "big_buy"}]
        if not buys:
            return {"status": "skipped", "reason": "no buy signals"}
        text = insider_buy_alert_text(ticker, buys)
        payload = {
            "severity": "high",
            "title": f"Insider buy — {ticker.upper()}",
            "message": text,
            "company_id": ticker.upper(),
            "alert_id": f"insider-{ticker.upper()}",
        }
        if notifier is not None:
            return dict(notifier(payload))
        from app.services.notification_service import NotificationService

        return dict(NotificationService()._dispatch_telegram(settings, payload))
    except Exception as exc:  # noqa: BLE001 — notificar jamas rompe el flujo
        return {"status": "skipped", "reason": f"{type(exc).__name__}: {exc}"}
