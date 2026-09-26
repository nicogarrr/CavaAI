"""NotificationService contract tests.

Alert delivery must be honest per channel: in_app always delivers,
unconfigured channels say so explicitly, failures are recorded without
leaking URLs or bodies, and every attempt is persisted on the alert.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.models.entities import AlertDelivery, Base, Company, ResearchAlert
from app.services import notification_service
from app.services.notification_service import NotificationService

STALE_CLAIM_SECONDS = getattr(notification_service, "STALE_CLAIM_SECONDS", 600)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.info["tenant_id"] = "tenant-test"
        yield session


def _alert(db: Session, channels: list[str], metadata: dict | None = None) -> ResearchAlert:
    company = Company(
        ticker="AAPL", name="Apple", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company)
    db.flush()
    alert = ResearchAlert(
        company_id=company.id, alert_type="price_above", severity="high",
        title="AAPL: price_above > 200", message="AAPL rule matched: observed=210",
        fingerprint="fp-test-1", channels=channels, metadata_=metadata or {},
    )
    db.add(alert)
    db.commit()
    return alert


def test_in_app_delivers_and_unconfigured_channels_say_so(db):
    alert = _alert(db, ["in_app", "email", "push"])
    deliveries = NotificationService().dispatch(db, alert)

    assert deliveries["in_app"]["status"] == "delivered"
    assert deliveries["email"]["status"] == "not_configured"
    assert deliveries["push"]["status"] == "not_configured"
    assert "No webhook configured" in deliveries["email"]["error"]
    # Every attempt persisted on the alert row.
    db.refresh(alert)
    assert set(alert.metadata_["deliveries"]) == {"in_app", "email", "push"}
    for entry in alert.metadata_["deliveries"].values():
        datetime.fromisoformat(entry["attempted_at"])


def test_telegram_not_configured_without_credentials(db):
    alert = _alert(db, ["telegram"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["telegram"]["status"] == "not_configured"
    assert "TELEGRAM_ENABLED" in deliveries["telegram"]["error"]


def test_configured_telegram_failure_does_not_leak_token_or_url(monkeypatch, db):
    token = "telegram-secret-token"
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    class _FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            raise RuntimeError(f"request to {url} failed for {json}")

    monkeypatch.setattr(notification_service.httpx, "Client", _FailingClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_enabled=True,
            telegram_bot_token=token,
            telegram_chat_id="12345",
            telegram_api_base_url="https://api.telegram.org",
            telegram_timeout_seconds=10,
        ),
    )

    deliveries = NotificationService().dispatch(db, _alert(db, ["telegram"]))

    assert deliveries["telegram"]["status"] == "unknown"
    error = deliveries["telegram"]["error"]
    assert "RuntimeError" in error
    assert token not in error
    assert endpoint not in error


def test_webhook_failure_does_not_persist_url_or_body(monkeypatch, db):
    endpoint = "https://hooks.example/secret?token=private"

    class _FailingClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            raise RuntimeError(f"request {url} failed with {json}")

    monkeypatch.setattr(notification_service.httpx, "Client", _FailingClient)
    monkeypatch.setattr(
        notification_service,
        "get_settings",
        lambda: SimpleNamespace(
            alert_email_webhook_url=endpoint,
            alert_push_webhook_url=endpoint,
        ),
    )

    deliveries = NotificationService().dispatch(db, _alert(db, ["email", "push"]))
    for channel in ("email", "push"):
        # RuntimeError generico: ambiguo (no se sabe si el proveedor acepto).
        assert deliveries[channel]["status"] == "unknown"
        assert deliveries[channel]["error"] == "RuntimeError"
        assert endpoint not in deliveries[channel]["error"]


def test_telegram_text_format_and_jev_line():
    payload = {
        "severity": "high", "title": "AAPL price alert", "message": "matched",
        "company_id": 7, "alert_id": 42,
        "jev_urgency": {"label": "urgent", "confidence": 0.9},
    }
    text = NotificationService._telegram_text(payload)
    assert text.startswith("[HIGH] AAPL price alert")
    assert "Alert id: 42" in text
    assert "Jev urgency: urgent (conf 0.90)" in text

    # No Jev metadata: no Jev line (fallback stays silent, never fabricated).
    payload["jev_urgency"] = {}
    assert "Jev urgency" not in NotificationService._telegram_text(payload)
    # Telegram plain-text cap.
    payload["message"] = "x" * 9000
    assert len(NotificationService._telegram_text(payload)) <= 4090


def _webhook_settings():
    return SimpleNamespace(
        telegram_enabled=False,
        telegram_bot_token=None,
        telegram_chat_id=None,
        telegram_api_base_url="https://api.telegram.org",
        telegram_timeout_seconds=10,
        alert_email_webhook_url="https://hooks.example/email",
        alert_push_webhook_url="https://hooks.example/push",
    )


class _CountingClient:
    """httpx.Client stub that counts POSTs per URL and always succeeds."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        type(self).calls.append(url)
        return SimpleNamespace(raise_for_status=lambda: None)


def test_dispatch_claims_delivery_row_before_sending(monkeypatch, db):
    """Outbox con claim: cuando el POST sale, la fila ya consta 'sending'."""
    _CountingClient.calls = []
    observed_states: list[str] = []

    class _InspectingClient(_CountingClient):
        def post(self, url, json):
            row = db.execute(
                select(AlertDelivery).where(
                    AlertDelivery.alert_id == json["alert_id"],
                    AlertDelivery.channel == json["channel"],
                )
            ).scalar_one()
            db.expire(row)
            observed_states.append(
                db.execute(
                    select(AlertDelivery.status).where(
                        AlertDelivery.id == row.id
                    )
                ).scalar_one()
            )
            return super().post(url, json)

    monkeypatch.setattr(notification_service.httpx, "Client", _InspectingClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    deliveries = NotificationService().dispatch(db, _alert(db, ["email", "push"]))

    assert observed_states == ["sending", "sending"]
    assert deliveries["email"]["status"] == "delivered"
    assert deliveries["push"]["status"] == "delivered"


def test_retry_after_failed_commit_does_not_resend(monkeypatch, db):
    """Commit que falla JUSTO tras un envio: el retry NO reenvia ese canal.

    La fila queda en 'sending' (claim persistido antes de enviar) y un retry
    inmediato no la reclama. El canal queda pendiente de recuperacion por
    claim expirado, nunca de reenvio inmediato.
    """
    _CountingClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _CountingClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email", "push"])
    real_commit = db.commit
    failed = {"done": False}

    def flaky_commit():
        # Falla el primer commit intentado DESPUES de un POST (el commit del
        # resultado post-envio), da igual cuantos commits internos haya antes.
        if _CountingClient.calls and not failed["done"]:
            failed["done"] = True
            raise RuntimeError("db connection lost mid-dispatch")
        return real_commit()

    monkeypatch.setattr(db, "commit", flaky_commit)

    with pytest.raises(RuntimeError, match="db connection lost"):
        NotificationService().dispatch(db, alert)
    db.rollback()
    monkeypatch.setattr(db, "commit", real_commit)

    # email quedo 'sending' (su POST salio, el commit del resultado fallo).
    row = db.execute(
        select(AlertDelivery).where(
            AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email"
        )
    ).scalar_one()
    assert row.status == "sending"

    deliveries = NotificationService().dispatch(db, alert)

    # email NO se reenvia: sigue 'sending' (claim vivo), ningun POST nuevo.
    # push nunca se envio: se reclama y entrega con normalidad (1 POST).
    assert deliveries["email"]["status"] == "sending"
    assert deliveries["push"]["status"] == "delivered"
    assert _CountingClient.calls.count("https://hooks.example/email") == 1
    assert _CountingClient.calls.count("https://hooks.example/push") == 1


def test_two_workers_cannot_send_the_same_channel_twice(monkeypatch, tmp_path):
    """Dos workers concurrentes: un solo POST por canal (claim atomico)."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/race.db", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)

    _CountingClient.calls = []
    lock = threading.Lock()

    class _SlowClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, json):
            time.sleep(0.2)  # ventana para que el otro worker intente el claim
            with lock:
                _CountingClient.calls.append(url)
            return SimpleNamespace(raise_for_status=lambda: None)

    monkeypatch.setattr(notification_service.httpx, "Client", _SlowClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    with Session(engine) as session:
        alert = _alert(session, ["email"])
        alert_id = alert.id

    errors: list[Exception] = []

    def worker():
        try:
            with Session(engine) as session:
                alert = session.get(ResearchAlert, alert_id)
                NotificationService().dispatch(session, alert)
        except Exception as exc:  # pragma: no cover - failure path asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    # Un solo POST aunque los dos workers despacharon la misma alerta.
    assert _CountingClient.calls.count("https://hooks.example/email") == 1
    with Session(engine) as session:
        row = session.execute(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == alert_id, AlertDelivery.channel == "email"
            )
        ).scalar_one()
        assert row.status == "delivered"
        assert row.attempts == 1


def test_stale_claim_becomes_eligible_after_ttl(monkeypatch, db):
    """Claim expirado (worker muerto): recuperable pasado STALE_CLAIM_SECONDS.

    Es el residuo at-least-once documentado: si el envio original llego, la
    recuperacion puede repetir ESE canal una vez.
    """
    _CountingClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _CountingClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    NotificationService().dispatch(db, alert)  # 1er POST (queda delivered)
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email")
        .values(
            status="sending",
            updated_at=datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS + 5),
        )
    )
    db.commit()

    deliveries = NotificationService().dispatch(db, alert)

    assert deliveries["email"]["status"] == "delivered"
    assert _CountingClient.calls.count("https://hooks.example/email") == 2
    row = db.execute(
        select(AlertDelivery).where(
            AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email"
        )
    ).scalar_one()
    assert row.attempts == 2


class _TimeoutClient:
    """Timeout tras enviar: el proveedor pudo aceptar. Resultado ambiguo."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        type(self).calls.append(url)
        import httpx as _httpx

        request = _httpx.Request("POST", url, json=json)
        raise _httpx.ReadTimeout("read timed out", request=request)


class _RejectedClient:
    """400 del proveedor: rechazo inequivoco (nunca se entregara tal cual)."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        import httpx as _httpx

        type(self).calls.append(url)
        request = _httpx.Request("POST", url, json=json)
        response = _httpx.Response(400, request=request)
        raise _httpx.HTTPStatusError("400 Bad Request", request=request, response=response)


class _ThrottledClient:
    """429 del proveedor: pidio esperar. No entregado, pero enfria."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        import httpx as _httpx

        type(self).calls.append(url)
        request = _httpx.Request("POST", url, json=json)
        response = _httpx.Response(429, request=request, headers={"Retry-After": "30"})
        raise _httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


class _ConnectErrorClient:
    """La conexion nunca se establecio: inequivoco, no salio nada."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        import httpx as _httpx

        type(self).calls.append(url)
        request = _httpx.Request("POST", url, json=json)
        raise _httpx.ConnectError("connection refused", request=request)


def test_timeout_is_ambiguous_and_not_retried_immediately(monkeypatch, db):
    """Timeout tras posible aceptacion remota: 'unknown', sin reintento
    inmediato (reintentar duplicaria si el proveedor ya entrego)."""
    _TimeoutClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _TimeoutClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "unknown"
    assert deliveries["email"]["error"] == "ReadTimeout"

    # Retry inmediato: NO reclama (ambiguos enfrian como 'sending').
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "unknown"
    assert _TimeoutClient.calls.count("https://hooks.example/email") == 1

    # Tras el TTL de claim expirado, la reconciliacion si reintenta (una vez).
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email")
        .values(
            updated_at=datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS + 5)
        )
    )
    db.commit()
    deliveries = NotificationService().dispatch(db, alert)
    assert _TimeoutClient.calls.count("https://hooks.example/email") == 2
    assert deliveries["email"]["status"] == "unknown"  # sigue fallando el stub


def test_4xx_rejection_is_permanent_and_never_retried(monkeypatch, db):
    """4xx (!= 429): el proveedor RECHAZO el mensaje tal cual. Reintentar el
    mismo cuerpo solo repite el rechazo: 'failed' es terminal, ni el retry
    inmediato ni el reconciliador lo reclaman jamas."""
    _RejectedClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _RejectedClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "failed"
    assert deliveries["email"]["error"] == "HTTPStatusError"

    # Retry inmediato: NO reclama (permanente).
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "failed"
    assert _RejectedClient.calls.count("https://hooks.example/email") == 1

    # Ni tras expirar el TTL ni via reconciliador.
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email")
        .values(
            updated_at=datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS + 5)
        )
    )
    db.commit()
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "failed"
    stats = NotificationService().reconcile_stale_deliveries(db)
    assert stats["candidates"] == 0
    assert _RejectedClient.calls.count("https://hooks.example/email") == 1


def test_connect_error_retries_immediately(monkeypatch, db):
    """ConnectError: la conexion nunca se establecio (inequivoco). La fila
    queda 'pending' y el retry inmediato reintenta sin cooldown."""
    _ConnectErrorClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _ConnectErrorClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "pending"
    assert deliveries["email"]["error"] == "ConnectError"

    NotificationService().dispatch(db, alert)
    assert _ConnectErrorClient.calls.count("https://hooks.example/email") == 2


def test_429_throttled_cools_down_and_reconciles(monkeypatch, db):
    """429: no entregado, pero el reintento inmediato solo empeora el rate
    limit. Enfria como 'sending'; vuelve via reconciliador tras el TTL."""
    _ThrottledClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _ThrottledClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "throttled"
    assert deliveries["email"]["error"] == "HTTPStatusError"

    # Retry inmediato: NO reclama (enfriando).
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "throttled"
    assert _ThrottledClient.calls.count("https://hooks.example/email") == 1

    # Reconciliador tras el TTL: si reintenta.
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id, AlertDelivery.channel == "email")
        .values(
            updated_at=datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS + 5)
        )
    )
    db.commit()
    stats = NotificationService().reconcile_stale_deliveries(db)
    assert stats["candidates"] == 1
    assert stats["redispatched"] == 1
    assert _ThrottledClient.calls.count("https://hooks.example/email") == 2


class _LongThrottleClient:
    """429 con Retry-After superior al cooldown fijo (900 > 600)."""

    calls: list[str] = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, json):
        import httpx as _httpx

        type(self).calls.append(url)
        request = _httpx.Request("POST", url, json=json)
        response = _httpx.Response(429, request=request, headers={"Retry-After": "900"})
        raise _httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


def test_retry_after_longer_than_cooldown_defers_claim(monkeypatch, db):
    """Retry-After=900 > STALE_CLAIM_SECONDS: la elegibilidad del claim se
    fija en el futuro; ni el reconciliador reintenta dentro de la ventana
    del proveedor (a los ~605s), y si lo hace pasada (a los ~905s)."""
    _LongThrottleClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _LongThrottleClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["status"] == "throttled"
    assert deliveries["email"]["retry_after"] == 900

    row = db.execute(
        select(AlertDelivery).where(AlertDelivery.alert_id == alert.id)
    ).scalar_one()
    stored = row.updated_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=UTC)
    assert stored > datetime.now(UTC)  # elegibilidad empujada al futuro

    # Simula ~605s transcurridos: aun dentro de la ventana Retry-After.
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id)
        .values(updated_at=stored - timedelta(seconds=605))
    )
    db.commit()
    stats = NotificationService().reconcile_stale_deliveries(db)
    assert stats["candidates"] == 0
    assert _LongThrottleClient.calls.count("https://hooks.example/email") == 1

    # Simula ~905s transcurridos: ventana respetada, reconciliador reintenta.
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == alert.id)
        .values(updated_at=stored - timedelta(seconds=905))
    )
    db.commit()
    stats = NotificationService().reconcile_stale_deliveries(db)
    assert stats["candidates"] == 1
    assert _LongThrottleClient.calls.count("https://hooks.example/email") == 2


def test_retry_after_is_capped(monkeypatch, db):
    """Retry-After por encima del cap se trunca: no se afirma cumplimiento
    del header mas alla de RETRY_AFTER_CAP_SECONDS."""

    class _HugeThrottleClient(_LongThrottleClient):
        calls: list[str] = []

        def post(self, url, json):
            import httpx as _httpx

            type(self).calls.append(url)
            request = _httpx.Request("POST", url, json=json)
            response = _httpx.Response(
                429, request=request, headers={"Retry-After": "7200"}
            )
            raise _httpx.HTTPStatusError(
                "429 Too Many Requests", request=request, response=response
            )

    monkeypatch.setattr(notification_service.httpx, "Client", _HugeThrottleClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    alert = _alert(db, ["email"])
    deliveries = NotificationService().dispatch(db, alert)
    assert deliveries["email"]["retry_after"] == notification_service.RETRY_AFTER_CAP_SECONDS


def test_reconciler_skips_fresh_rows_and_redispatches_stale_unknown(monkeypatch, db):
    """El reconciliador solo toca claims expirados: filas 'unknown' frescas
    (aun enfriando) y entregadas quedan intactas."""
    _TimeoutClient.calls = []
    monkeypatch.setattr(notification_service.httpx, "Client", _TimeoutClient)
    monkeypatch.setattr(notification_service, "get_settings", _webhook_settings)

    stale_alert = _alert(db, ["email"])
    NotificationService().dispatch(db, stale_alert)
    company2 = Company(
        ticker="MSFT", name="Microsoft", exchange="NASDAQ", currency="USD",
        sector="Tech", industry="Tech", company_type="holding",
        valuation_model="unassigned", special_sources=[], special_risks=[], factor_tags=[],
    )
    db.add(company2)
    db.flush()
    fresh_alert = ResearchAlert(
        company_id=company2.id, alert_type="price_above", severity="high",
        title="MSFT: price_above > 400", message="MSFT rule matched: observed=410",
        fingerprint="fp-test-2", channels=["email"], metadata_={},
    )
    db.add(fresh_alert)
    db.commit()
    NotificationService().dispatch(db, fresh_alert)

    # Solo la primera envejece mas alla del TTL.
    db.execute(
        update(AlertDelivery)
        .where(AlertDelivery.alert_id == stale_alert.id)
        .values(
            updated_at=datetime.now(UTC) - timedelta(seconds=STALE_CLAIM_SECONDS + 5)
        )
    )
    db.commit()

    stats = NotificationService().reconcile_stale_deliveries(db)
    assert stats["candidates"] == 1
    assert stats["redispatched"] == 1
    # 1 envio inicial por alerta + 1 reintento reconciliado = 3 totales.
    assert _TimeoutClient.calls.count("https://hooks.example/email") == 3

    # La fila fresca sigue 'unknown' y no fue reclamada.
    fresh_row = db.execute(
        select(AlertDelivery).where(AlertDelivery.alert_id == fresh_alert.id)
    ).scalar_one()
    assert fresh_row.status == "unknown"
    assert fresh_row.attempts == 1
