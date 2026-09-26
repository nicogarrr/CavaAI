"""Un GET no debe escribir en la base de datos.

Dos endpoints hacian efectos de estado en un GET:

- `GET /api/alerts` reabria las alertas cuyo snooze habia caducado y hacia
  commit. Dos GET seguidos no daban el mismo resultado, cualquier cache HTTP de
  la ruta quedaba envenenada, y un fallo de la escritura devolvia un 500 en un
  camino de solo lectura.

- `GET /api/taxes/report/{year}?regenerate=true` persistia un TaxReport. El
  calculo forzado ya tiene su propio POST, asi que el parametro solo servia
  para tener dos caminos distintos para lo mismo.

Ademas, el filtro de alertas snoozadas escondia para siempre las que no tienen
fecha de caducidad: `status != 'snoozed'` es FALSE y `snoozed_until <= now` es
NULL, luego `FALSE OR NULL` = NULL y la fila no pasa el WHERE.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.core.database import SessionLocal, init_db
from app.models import Company, ResearchAlert

from tests.auth_helpers import auth_settings, signed_request
from tests.conftest import _TEST_ISOLATED_ENV_DEFAULTS  # noqa: F401  (env hermetico)

SECRET = "mutating-gets-secret-with-at-least-32-characters"
REQUEST_TENANT = "tenant-gets"


def _tenant_id_for(db, external_id: str = REQUEST_TENANT) -> int:
    """Id numerico del tenant que creara la peticion firmada.

    get_db auto-provisiona el Tenant por external_id, asi que el fixture tiene
    que sembrar las filas con ESE id, no con uno arbitrario.
    """
    from app.models import Tenant

    db.info["tenant_id"] = None
    tenant = db.scalar(select(Tenant).where(Tenant.external_id == external_id))
    if tenant is None:
        tenant = Tenant(external_id=external_id, name="Alerts GET Co")
        db.add(tenant)
        db.commit()
    return tenant.id


def _setting() -> None:
    import os

    for key, value in _TEST_ISOLATED_ENV_DEFAULTS.items():
        os.environ[key] = value
    os.environ["RESEARCH_AUTH_SECRET"] = SECRET


def _company(db) -> Company:
    ticker = "TGET"
    db.info["tenant_id"] = _tenant_id_for(db)
    existing = db.scalar(select(Company).where(Company.ticker == ticker))
    if existing is not None:
        # Se registra tambien la preexistente: si una corrida anterior la dejo
        # en la base compartida, este test sigue siendo responsable de limpiarla.
        _CREATED_COMPANIES.append(existing.id)
        return existing
    company = Company(
        ticker=ticker,
        name="Mutating GET Co",
        exchange="TEST",
        currency="USD",
        sector="Software",
        industry="Application Software",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(company)
    db.commit()
    _CREATED_COMPANIES.append(company.id)
    return company


_CREATED_COMPANIES: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup_alert_fixtures():
    """No dejar empresas sueltas.

    test_calculated_metrics.py selecciona pares por similitud de sector y
    descarte cualquier empresa extra que encuentre en la base, asi que una
    company de mas cambia su resultado. La base de tests es compartida.
    """
    yield
    if not _CREATED_COMPANIES:
        return
    from sqlalchemy import delete

    db = SessionLocal()
    try:
        for company_id in _CREATED_COMPANIES:
            db.execute(delete(ResearchAlert).where(ResearchAlert.company_id == company_id))
            company = db.get(Company, company_id)
            if company is not None:
                db.delete(company)
        db.commit()
    finally:
        db.close()
        _CREATED_COMPANIES.clear()


def _alert(db, company: Company, status: str, snoozed_until=None, tag: str = "") -> ResearchAlert:
    """Siembra una alerta. Idempotente: el unique es (tenant_id, fingerprint)."""
    fingerprint = f"fp-{status}-{snoozed_until}-{tag}"
    existing = db.scalar(
        select(ResearchAlert).where(ResearchAlert.fingerprint == fingerprint)
    )
    if existing is not None:
        return existing
    alert = ResearchAlert(
        company_id=company.id,
        severity="medium",
        status=status,
        alert_type="manual",
        title="T",
        message="M",
        fingerprint=fingerprint,
        channels=["in_app"],
        metadata_={},
        snoozed_until=snoozed_until,
    )
    db.add(alert)
    db.commit()
    return alert


# --------------------------------------------------------------------------
# Sintaxis: ningun handler GET con db.commit()
# --------------------------------------------------------------------------


def test_no_get_handler_commits():
    """Guarda estructural sobre TODAS las rutas, no solo las queCambiamos."""
    routes = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "routes"
    offenders: list[str] = []
    for path in sorted(routes.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            methods = [
                d.args[0].value
                for d in node.decorator_list
                if isinstance(d, ast.Call)
                and getattr(d.func, "attr", "") in {"get", "post", "put", "patch", "delete"}
                and d.args
                and isinstance(d.args[0], ast.Constant)
            ]
            if "get" not in methods:
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", "") == "commit"
                ):
                    offenders.append(f"{path.name}:{inner.lineno} en {node.name}")
    assert offenders == [], f"GET que escribe: {offenders}"


def test_tax_report_get_has_no_regenerate_parameter():
    from app.api.routes import taxes

    signature = inspect.signature(taxes.tax_report)
    assert "regenerate" not in signature.parameters
    # Y el POST sigue existiendo para el calculo forzado.
    assert "regenerate_tax_report" in dir(taxes)


def test_list_alerts_does_not_commit():
    from app.api.routes import alerts

    assert "db.commit()" not in inspect.getsource(alerts.list_alerts)


# --------------------------------------------------------------------------
# Comportamiento
# --------------------------------------------------------------------------


def test_list_alerts_is_repeatable(monkeypatch):
    init_db()
    from app.core import auth as auth_module

    _setting()
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=SECRET, app_env="local"),
    )

    db = SessionLocal()
    try:
        company = _company(db)
        past = datetime.now(UTC) - timedelta(days=1)
        alert = _alert(db, company, "snoozed", past, tag="past")
        alert_id = alert.id
    finally:
        db.close()

    client = TestClient(main.app)
    tenant = "tenant-gets"
    first = signed_request(client, SECRET, tenant, "u", "GET", "/api/alerts")
    second = signed_request(client, SECRET, tenant, "u", "GET", "/api/alerts")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json(), "el GET no es idempotente"

    # Y la fila NO se toco: la transicion la hace el worker de reglas.
    db = SessionLocal()
    try:
        stored = db.get(ResearchAlert, alert_id)
        assert stored.status == "snoozed", "el GET escribio en la base de datos"
    finally:
        db.close()


def test_snoozed_alert_without_expiry_is_still_visible(monkeypatch):
    """Una alerta snoozada sin fecha de caducidad no se esconde para siempre."""
    init_db()
    from app.core import auth as auth_module

    _setting()
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=SECRET, app_env="local"),
    )

    db = SessionLocal()
    try:
        company = _company(db)
        alert = _alert(db, company, "snoozed", None, tag="nforever")
        alert_id = alert.id
    finally:
        db.close()

    client = TestClient(main.app)
    response = signed_request(
        client, SECRET, REQUEST_TENANT, "u", "GET", "/api/alerts"
    )
    assert response.status_code == 200, response.text
    assert alert_id in {item["id"] for item in response.json()}

    db = SessionLocal()
    try:
        assert db.get(ResearchAlert, alert_id).status == "snoozed"
    finally:
        db.close()


def test_expired_snooze_is_reported_as_open_without_writing(monkeypatch):
    init_db()
    from app.core import auth as auth_module

    _setting()
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: auth_settings(strict=True, secret=SECRET, app_env="local"),
    )

    db = SessionLocal()
    try:
        company = _company(db)
        alert = _alert(db, company, "snoozed", datetime.now(UTC) - timedelta(days=1), tag="expired")
        alert_id = alert.id
    finally:
        db.close()

    client = TestClient(main.app)
    response = signed_request(
        client, SECRET, REQUEST_TENANT, "u", "GET", "/api/alerts"
    )
    assert response.status_code == 200, response.text
    payload = next(item for item in response.json() if item["id"] == alert_id)
    # El estado derivado se refleja en la respuesta...
    assert payload["status"] == "open"
    assert payload["snoozed_until"] is None

    db = SessionLocal()
    try:
        # ...pero la fila sigue como estaba.
        stored = db.get(ResearchAlert, alert_id)
        assert stored.status == "snoozed"
        assert stored.snoozed_until is not None
    finally:
        db.close()
