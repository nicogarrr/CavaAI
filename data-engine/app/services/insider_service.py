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

from datetime import UTC, date, datetime
from typing import Any, Callable

from app.core.config import get_settings
from app.services.connectors import form4 as form4_connector

CLUSTER_MIN_INSIDERS = 3
CLUSTER_WINDOW_DAYS = 30
BIG_BUY_THRESHOLD_USD = 1_000_000.0

_CEO_TOKENS = ("chief executive", "ceo", "president")
_CFO_TOKENS = ("chief financial", "cfo")


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


def _is_c_suite(tx: dict) -> bool:
    title = str(tx.get("officer_title") or "").lower()
    role = str(tx.get("role") or "").lower()
    haystack = f"{title} {role}"
    return any(tok in haystack for tok in (*_CEO_TOKENS, *_CFO_TOKENS))


def _is_ceo(tx: dict) -> bool:
    haystack = f"{tx.get('officer_title') or ''} {tx.get('role') or ''}".lower()
    return any(tok in haystack for tok in _CEO_TOKENS)


def _is_cfo(tx: dict) -> bool:
    haystack = f"{tx.get('officer_title') or ''} {tx.get('role') or ''}".lower()
    return any(tok in haystack for tok in _CFO_TOKENS)


def open_market_buys(transactions: list[dict]) -> list[dict]:
    """Compras por codigo P + adquirida (mercado abierto O privadas)."""
    return [tx for tx in transactions if form4_connector.is_open_market_buy(tx)]


def detect_signals(transactions: list[dict]) -> list[dict]:
    """Detecta cluster_buy, c_suite_buy y big_buy sobre transacciones Form 4."""
    buys = open_market_buys(transactions)
    signals: list[dict] = []

    for tx in buys:
        value = tx.get("value")
        try:
            amount = float(value) if value is not None else None
        except (TypeError, ValueError):
            amount = None
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
                total = sum(float(tx.get("value") or 0) for tx in window)
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
                    xml_text = form4_connector.fetch_filing_xml(
                        filing["document_url"], client=client
                    )
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
        result: dict = {
            "ticker": wanted,
            "cik": resolved_cik,
            "status": "ok",
            "filings_scanned": len(filings[:limit]),
            "buy_count": len(open_market_buys(transactions)),
            "signals": signals,
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        if errors:
            result["filing_errors"] = errors
        return result
    except Exception as exc:  # noqa: BLE001 — el endpoint nunca debe romper
        return {"ticker": wanted, "status": "degraded",
                "reason": f"{type(exc).__name__}: {exc}", "signals": []}


def _cik_for_ticker(ticker: str, client=None) -> str | None:
    """Resuelve el CIK via company_tickers.json (inyectable en tests)."""
    import httpx as _httpx

    url = "https://www.sec.gov/files/company_tickers.json"
    headers = form4_connector.default_headers()
    if client is not None:
        response = client.get(url, headers=headers)
    else:
        with _httpx.Client(timeout=30, headers=headers) as owned:
            response = owned.get(url)
    response.raise_for_status()
    for entry in response.json().values():
        if isinstance(entry, dict) and str(entry.get("ticker", "")).upper() == ticker:
            return str(entry["cik_str"]).zfill(10)
    return None


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
