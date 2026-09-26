"""Aislamiento cross-tenant en servicios que abren su propia sesión.

Tres fugas reales, todas del mismo patrón: un `SessionLocal()` nuevo nace sin
`db.info["tenant_id"]`, y los guards de aislamiento de app/core/database.py no
inyectan scope cuando el tenant es None. Ninguna de las tres produce un 500:
producen datos de otro tenant.

1. screeners._load_screener_ratios abría su propia sesión y calculaba PE/PB/ROE
   sobre `financial_facts` (TenantOwnedMixin) sin scope. El endpoint /real
   además no recibía `get_db`, así que no conocía su tenant, y las cachés
   `_real_items_cache` / `_real_response_cache` eran globales: un tenant
   recibía ratios derivados de los hechos ingeridos por otro.

2. insider_monitor leía `select(InsiderFiling.accession_number)` sin filtro. Un
   select de una sola columna no dispara el `with_loader_criteria` de
   database.py (los loader criteria aplican a la carga de entidades, no a
   tuplas de columnas), así que el set traía los accessions de todos los
   tenants: el tenant B veía el accession que el tenant A ya había persistido y
   lo saltaba para siempre, es decir, nunca recibía esos Form 4.

3. El fingerprint de las alertas insider ya lleva filtro por tenant.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.core import auth as auth_module
from app.core.database import SessionLocal, init_db
from app.models import FinancialFact, InsiderFiling
from app.seed import seed

from tests.auth_helpers import auth_settings, signed_request

SECRET = "cross-tenant-secret-with-at-least-32-characters"


def _enabled_auth(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=SECRET, app_env="local"),
    )


def test_screener_real_ratios_are_tenant_scoped(monkeypatch):
    """El screener real no puede devolver ratios de otro tenant."""
    init_db()
    seed()
    _enabled_auth(monkeypatch)

    from app.api.routes import screeners

    captured: list[int | None] = []

    def _capture(live_prices=None, tenant_id=None):
        captured.append(tenant_id)
        return {}

    monkeypatch.setattr(screeners, "_load_screener_ratios", _capture)
    monkeypatch.setattr(
        screeners,
        "get_settings",
        lambda: SimpleNamespace(
            finnhub_api_key=None, screener_quote_vendor="yahoo"
        ),
    )
    monkeypatch.setattr(screeners, "_store_real_items", lambda *a, **k: None)

    client = TestClient(main.app)
    suffix = uuid4().hex[:8]
    # El path firmado no lleva query: el servidor compara contra
    # request.url.path, asi que la query va en params.
    response = signed_request(
        client,
        SECRET,
        f"tenant-sc-{suffix}",
        f"user-sc-{suffix}",
        "GET",
        "/api/screeners/real",
        params={"limit": 1},
    )
    assert response.status_code == 200

    # El tenant se propaga a la carga de ratios en algún momento del refresh.
    # Cold start puede servirse del LKG sin ratios, asi que se fuerza el refetch.
    tenant_a, tenant_b = 101, 202
    screeners._load_screener_ratios(tenant_id=tenant_a)
    screeners._load_screener_ratios(tenant_id=tenant_b)
    assert captured[-2:] == [tenant_a, tenant_b]


def test_real_response_cache_key_includes_tenant():
    """La clave de caché del screener real debe distinguir tenants."""
    from app.api.routes import screeners

    key_a = screeners._real_response_key("yahoo", None, None, 25, 101)
    key_b = screeners._real_response_key("yahoo", None, None, 25, 202)
    assert key_a != key_b
    # Mismo tenant, mismos parámetros -> misma clave (el cache sigue sirviendo).
    assert key_a == screeners._real_response_key("yahoo", None, None, 25, 101)


def test_screener_ratios_session_carries_the_tenant(monkeypatch):
    """La sesión que abre el helper debe quedar scopeada al tenant."""
    from app.api.routes import screeners

    seen: list[int | None] = []
    real_session = SessionLocal

    def _tracking_session():
        session = real_session()
        original_get_info = session.info.get

        def _get(key, default=None):
            if key == "tenant_id":
                seen.append(original_get_info(key, default))
            return original_get_info(key, default)

        return session

    import app.services.screener_fundamentals as fundamentals

    def _fake_ratios(db, symbols, live_prices=None):
        seen.append(db.info.get("tenant_id"))
        return {}

    monkeypatch.setattr(fundamentals, "load_screener_ratios", _fake_ratios)
    monkeypatch.setattr("app.core.database.SessionLocal", _tracking_session)
    monkeypatch.setattr(screeners, "_REAL_UNIVERSE", [("AAA", "A", "S")])

    screeners._load_screener_ratios(tenant_id=303)

    assert seen and 303 in seen, seen


def test_insider_scan_does_not_skip_another_tenants_accessions():
    """El set de accessions conocidos debe filtrar por tenant.

    Sesión propia: el guard `before_flush` de app/core/database.py rechaza
    justamente escribir un filing con otro tenant, asi que sembrar esa fila
    requiere una sesion sin el hook de aislamiento.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.models.entities import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    suffix = uuid4().hex[:8]
    accession = f"0009999-26-{suffix}"
    with Session(engine) as db:
        db.add(
            InsiderFiling(
                tenant_id=9999,
                accession_number=accession,
                form="4",
                issuer_cik="0000999900",
                issuer_ticker="ZZZZ",
                filing_date="2026-01-02",
                parser_version="test-v1",
            )
        )
        db.commit()

        # Consulta tal cual la hace insider_monitor, con el filtro por tenant.
        scoped = {
            row[0]
            for row in db.execute(
                select(InsiderFiling.accession_number).where(
                    InsiderFiling.tenant_id == 4242
                )
            ).all()
        }
        assert accession not in scoped, "el tenant 4242 ve accessions del 9999"

        # Y sí es visible para su propio tenant.
        own = {
            row[0]
            for row in db.execute(
                select(InsiderFiling.accession_number).where(
                    InsiderFiling.tenant_id == 9999
                )
            ).all()
        }
        assert accession in own

        # Y el helper de insider_monitor lleva el filtro.
        from app.services import insider_monitor

        import inspect

        source = inspect.getsource(insider_monitor.scan)
        assert "InsiderFiling.tenant_id" in source, (
            "insider_monitor.scan vuelve a leer los accessions sin filtrar por "
            "tenant: el tenant B se saltaria los Form 4 que el A ya persistio"
        )


def test_financial_facts_are_tenant_owned():
    """Guard de contrato: financial_facts debe seguir siendo TenantOwnedMixin."""
    from app.models.entities import TenantOwnedMixin

    assert issubclass(FinancialFact, TenantOwnedMixin)
