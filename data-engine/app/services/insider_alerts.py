"""PR-4: outbox durable de alertas insider.

Evalua las transacciones Form 4 YA PERSISTIDAS (#82) y crea alertas
ResearchAlert deduplicadas. La clave de alerta es
`rule_version + regla + fingerprint de transaccion` — nunca el ticker — asi
una re-evaluacion (o una enmienda 4/A, que llega con fingerprints propios)
no duplica ni pierde alertas.

Reglas por defecto (rule_version="insider-v1"):
- big_buy: compra codigo P no derivada con valor >= 1M USD.
- c_suite_buy: compra codigo P de CEO/CFO (rol o titulo).
- cluster_buy: >=3 insiders distintos (por CIK) comprando codigo P el
  mismo ticker en una ventana de 30 dias.

Solo entran transacciones codigo P adquiridas NO derivadas: grants (A),
retenciones (F), regalos (G), ejercicios (M) y disclosures 10b5-1 quedan
fuera por construccion. El wording nunca afirma "mercado abierto": el
codigo P cubre compras abiertas Y privadas (#81).

Telegram es opt-in via settings.insider_alerts_enabled y jamas rompe la
evaluacion; el canal por defecto es in-app.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Company, InsiderTransaction, ResearchAlert
from app.services.insider_service import (
    BIG_BUY_THRESHOLD_USD,
    CLUSTER_MIN_INSIDERS,
    CLUSTER_WINDOW_DAYS,
    _is_c_suite,
    _parse_date,
)

RULE_VERSION = "insider-v1"
ALERT_TYPE_PREFIX = "insider_"


def _alert_fingerprint(rule: str, tx_fingerprint: str) -> str:
    raw = f"{RULE_VERSION}|{rule}|{tx_fingerprint}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _tx_as_signal_dict(tx: InsiderTransaction) -> dict:
    return {
        "ticker": tx.issuer_ticker,
        "insider": tx.insider,
        "role": tx.role,
        "officer_title": tx.officer_title,
        "date": tx.tx_date,
        "shares": tx.shares,
        "price": tx.price,
        "value": tx.value,
        "type": tx.code,
        "acquired_disposed": tx.acquired_disposed,
        "is_derivative": tx.is_derivative,
        "source_url": tx.source_url,
        "multi_reporter": tx.multi_reporter,
    }


def _candidate_purchases(db: Session, tenant_id: int | None) -> list[InsiderTransaction]:
    rows = db.scalars(
        select(InsiderTransaction).where(
            InsiderTransaction.tenant_id.is_(tenant_id) if tenant_id is None
            else InsiderTransaction.tenant_id == tenant_id,
            InsiderTransaction.code == "P",
            InsiderTransaction.acquired_disposed == "A",
            InsiderTransaction.is_derivative.is_(False),
        )
    ).all()
    return list(rows)


def _company_id_for(db: Session, ticker: str | None) -> int | None:
    if not ticker:
        return None
    company = db.scalar(select(Company).where(Company.ticker == ticker.upper()))
    return company.id if company else None


def _build_alerts(
    db: Session, purchases: list[InsiderTransaction]
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for tx in purchases:
        value = float(tx.value or 0)
        base = {
            "company_id": _company_id_for(db, tx.issuer_ticker),
            "tx_fingerprint": tx.fingerprint,
            "metadata": {
                "rule_version": RULE_VERSION,
                "accession_number": tx.accession_number,
                "form": tx.form,
                "insider_cik": tx.insider_cik,
                "tx_fingerprint": tx.fingerprint,
                "source_url": tx.source_url,
                "data_quality": tx.data_quality,
            },
        }
        if value >= BIG_BUY_THRESHOLD_USD:
            alerts.append(
                {
                    **base,
                    "rule": "big_buy",
                    "severity": "high",
                    "title": f"Compra insider grande — {tx.issuer_ticker or '?'}",
                    "message": (
                        f"{tx.insider or 'Insider'} compro ${value:,.0f} "
                        f"({tx.shares} acc. @ ${tx.price}) el {tx.tx_date}. "
                        "Codigo P: mercado abierto o privado; el XML no siempre lo distingue."
                    ),
                }
            )
        if _is_c_suite(_tx_as_signal_dict(tx)):
            alerts.append(
                {
                    **base,
                    "rule": "c_suite_buy",
                    "severity": "medium",
                    "title": f"Compra C-suite — {tx.issuer_ticker or '?'}",
                    "message": (
                        f"{tx.insider or 'Insider'} ({tx.officer_title or tx.role or 'directivo'}) "
                        f"compro ${value:,.0f} el {tx.tx_date}. "
                        "Codigo P: mercado abierto o privado."
                    ),
                }
            )

    # cluster_buy: por ticker, >=3 CIK distintos con compras P en 30 dias.
    by_ticker: dict[str, list[InsiderTransaction]] = {}
    for tx in purchases:
        if tx.issuer_ticker:
            by_ticker.setdefault(tx.issuer_ticker.upper(), []).append(tx)
    for ticker, txs in by_ticker.items():
        dated = sorted(
            ((d, tx) for tx in txs if (d := _parse_date(tx.tx_date)) is not None),
            key=lambda pair: pair[0],
        )
        for start in range(len(dated)):
            window = [
                tx for d, tx in dated
                if 0 <= (d - dated[start][0]).days <= CLUSTER_WINDOW_DAYS
            ]
            insiders = {tx.insider_cik or tx.insider for tx in window}
            if len(insiders) >= CLUSTER_MIN_INSIDERS:
                fp_source = "+".join(sorted(tx.fingerprint for tx in window))
                total = sum(float(tx.value or 0) for tx in window)
                alerts.append(
                    {
                        "company_id": _company_id_for(db, ticker),
                        "tx_fingerprint": hashlib.sha256(fp_source.encode()).hexdigest(),
                        "rule": "cluster_buy",
                        "severity": "high",
                        "title": f"Cluster de compras insider — {ticker}",
                        "message": (
                            f"{len(insiders)} insiders distintos compraron {ticker} "
                            f"en {CLUSTER_WINDOW_DAYS} dias (${total:,.0f} total). "
                            "Codigo P: mercado abierto o privado."
                        ),
                        "metadata": {
                            "rule_version": RULE_VERSION,
                            "insider_count": len(insiders),
                            "window_days": CLUSTER_WINDOW_DAYS,
                            "tx_fingerprints": [tx.fingerprint for tx in window],
                        },
                    }
                )
                break
    return alerts


def evaluate(
    db: Session,
    *,
    tenant_id: int | None = None,
    notifier: Callable[[dict], dict] | None = None,
) -> dict[str, Any]:
    """Evalua reglas sobre lo persistido y escribe el outbox. Nunca lanza."""
    stats: dict[str, Any] = {
        "status": "ok",
        "rule_version": RULE_VERSION,
        "candidates": 0,
        "alerts_created": 0,
        "alerts_existing": 0,
        "telegram_sent": 0,
        "errors": [],
    }
    try:
        purchases = _candidate_purchases(db, tenant_id)
        stats["candidates"] = len(purchases)
        if not purchases:
            return stats
        existing = {
            row[0]
            for row in db.execute(
                select(ResearchAlert.fingerprint).where(
                    ResearchAlert.tenant_id.is_(tenant_id) if tenant_id is None
                    else ResearchAlert.tenant_id == tenant_id,
                    ResearchAlert.alert_type.like(f"{ALERT_TYPE_PREFIX}%"),
                )
            ).all()
        }
        from app.core.config import get_settings

        telegram_enabled = bool(getattr(get_settings(), "insider_alerts_enabled", False))
        for alert in _build_alerts(db, purchases):
            fp = _alert_fingerprint(alert["rule"], alert["tx_fingerprint"])
            if fp in existing:
                stats["alerts_existing"] += 1
                continue
            channels = ["in_app"]
            record = ResearchAlert(
                tenant_id=tenant_id,
                company_id=alert["company_id"],
                severity=alert["severity"],
                status="open",
                alert_type=f"{ALERT_TYPE_PREFIX}{alert['rule']}",
                title=alert["title"],
                message=alert["message"],
                fingerprint=fp,
                channels=channels,
                metadata_=alert["metadata"],
            )
            db.add(record)
            db.commit()
            existing.add(fp)
            stats["alerts_created"] += 1
            if telegram_enabled:
                try:
                    payload = {
                        "severity": alert["severity"],
                        "title": alert["title"],
                        "message": alert["message"],
                        "alert_id": fp,
                    }
                    if notifier is not None:
                        notifier(payload)
                    else:
                        from app.services.notification_service import NotificationService

                        NotificationService()._dispatch_telegram(get_settings(), payload)
                    stats["telegram_sent"] += 1
                    record.channels = ["in_app", "telegram"]
                    db.add(record)
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - notificar jamas rompe
                    stats["errors"].append(f"telegram: {type(exc).__name__}")
        return stats
    except Exception as exc:  # noqa: BLE001 - el actor jamas recibe una excepcion
        stats["status"] = "error"
        stats["errors"].append(f"fatal: {type(exc).__name__}: {exc}")
        return stats
