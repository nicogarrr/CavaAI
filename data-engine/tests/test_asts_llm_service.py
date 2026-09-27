"""ASTS catalog LLM layer: real data only, honest 'sin datos', gated free model."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, Tenant
from app.services import asts_llm_quota as quota
from app.services import asts_llm_service as service
from app.services.asts_catalog_service import persist_catalog
from app.services.connectors.celestrak_ast import SOURCE_URL


def row(cat_id, name, epoch):
    return {"norad_cat_id": cat_id, "object_name": name, "object_id": f"2026-0{cat_id % 90}",
            "epoch": epoch.isoformat(), "mean_motion": 15.39, "eccentricity": 0.0007,
            "inclination": 53.22, "ra_of_asc_node": 277.6, "arg_of_pericenter": 121.8,
            "mean_anomaly": 238.3, "bstar": 0.00018, "mean_motion_dot": 6.6e-5,
            "mean_motion_ddot": 0.0}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add_all([Tenant(id=1, external_id="one"), Tenant(id=2, external_id="two")])
        session.commit()
    with factory() as session:
        session.info["tenant_id"] = 1
        yield session
    engine.dispose()


def fresh_catalog(db, *, age=timedelta(hours=1)):
    now = datetime.now(UTC)
    fetched = now - age
    catalog = [row(53807, "BLUEWALKER-3", fetched - timedelta(hours=20)),
               row(61045, "SPACEMOBILE-003", fetched - timedelta(hours=5)),
               row(61046, "SPACEMOBILE-004", fetched - timedelta(hours=2))]
    persist_catalog(db, catalog, fetched)
    return fetched


def test_stale_snapshot_reports_sin_datos_without_llm(db, monkeypatch):
    fetched = fresh_catalog(db, age=timedelta(hours=31))
    monkeypatch.setenv("ASTS_LLM_ENABLED", "1")
    monkeypatch.setattr(quota, "_LOCAL", {})
    result = service.analyze_asts_catalog(db)
    assert result["status"] == "sin datos"
    assert result["analysis"] is None and result["mode"] is None
    assert result["stale_snapshot_at"] == fetched.isoformat()
    assert result["llm_quota"] is None  # ni reserva sin datos frescos
    assert "30 h" in result["note"]
    assert result["source"]["url"] == SOURCE_URL  # igualdad exacta, no substring


def test_fresh_catalog_deterministic_when_flag_off(db, monkeypatch):
    fetched = fresh_catalog(db)
    monkeypatch.delenv("ASTS_LLM_ENABLED", raising=False)
    result = service.analyze_asts_catalog(db)
    assert result["status"] == "disponible" and result["mode"] == "determinista"
    assert result["note"] == "Análisis LLM desactivado por configuración."
    assert result["llm_quota"] is None
    assert result["analysis"]["llm_interpretation"] is None
    agg = result["analysis"]["aggregates"]
    assert agg["count"] == 3
    assert agg["families"] == {"BLUEWALKER": 1, "SPACEMOBILE": 2}
    assert agg["epoch_max"] in result["analysis"]["summary"]
    assert fetched.isoformat() in result["analysis"]["summary"]
    assert "CelesTrak" in result["analysis"]["summary"]
    # solo datos reales: cada observación cita valores del catálogo
    for obs in result["analysis"]["observations"]:
        assert any(token in obs["text"] for token in ("53.22", "15.39", "SPACEMOBILE", "epoch", "Época"))


def test_llm_failure_falls_back_honestly(db, monkeypatch):
    fresh_catalog(db)
    monkeypatch.setenv("ASTS_LLM_ENABLED", "1")
    monkeypatch.setattr(service, "reserve_llm_call", lambda *_args: {
        "allowed": True, "minute_used": 1, "minute_limit": 2,
        "day_used": 1, "day_limit": 30, "reset": "UTC calendar minute/day"})
    def boom(_payload):
        raise RuntimeError("provider down")
    monkeypatch.setattr(service, "_analyze_with_llm", boom)
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "determinista"
    assert result["note"] == "Análisis LLM no disponible; se usa el resumen determinista."
    assert result["analysis"]["aggregates"]["count"] == 3


def stub_llm(monkeypatch, summary, observations=()):
    monkeypatch.setenv("ASTS_LLM_ENABLED", "1")
    monkeypatch.setattr(service, "reserve_llm_call", lambda *_args: {
        "allowed": True, "minute_used": 1, "minute_limit": 2,
        "day_used": 1, "day_limit": 30, "reset": "UTC calendar minute/day"})
    async def fake(_payload):
        return service.AstsAnalysis(
            summary=summary,
            observations=[service.Observation(text=o) for o in observations]), object()
    monkeypatch.setattr(service, "_analyze_with_llm", fake)


def test_llm_success_marks_mode_and_keeps_aggregates(db, monkeypatch):
    fetched = fresh_catalog(db)
    stub_llm(monkeypatch,
             f"Catálogo CelesTrak descargado el {fetched.isoformat()}: 3 objetos.",
             ["Inclinación uniforme de 53.22°."])
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "llm"
    assert result["llm_input"] == "completo"
    # el resumen canonico es SIEMPRE el determinista, tambien en modo llm
    assert result["analysis"]["summary"].startswith("Catálogo CelesTrak del grupo AST descargado el")
    assert result["analysis"]["aggregates"]["count"] == 3  # datos reales siempre presentes
    interp = result["analysis"]["llm_interpretation"]
    assert interp["summary"].startswith("Catálogo CelesTrak descargado el")
    assert "no verificada" in interp["disclaimer"]
    assert result["llm_quota"]["day_limit"] == 30


def test_llm_rounded_values_are_accepted(db, monkeypatch):
    fetched = fresh_catalog(db)
    # 53.2 es un redondeo legitimo de la inclinacion real 53.22
    stub_llm(monkeypatch,
             f"Catálogo CelesTrak descargado el {fetched.isoformat()[:10]}: 3 objetos.",
             ["Inclinación de 53.2° en todo el catálogo."])
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "llm"
    assert result["analysis"]["llm_interpretation"]["observations"][0]["text"].startswith("Inclinación de 53.2")


def test_llm_invented_number_falls_back_to_deterministic(db, monkeypatch):
    fetched = fresh_catalog(db)
    stub_llm(monkeypatch,
             f"Catálogo CelesTrak descargado el {fetched.isoformat()[:10]}: 200 satélites operativos.")
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "determinista"
    assert result["note"] == ("Interpretación generativa descartada: incluía datos "
                              "no contrastados con el catálogo.")
    assert result["analysis"]["llm_interpretation"] is None
    # el canonico sigue siendo el determinista con los valores reales
    assert result["analysis"]["summary"].startswith("Catálogo CelesTrak del grupo AST descargado el")
    assert result["analysis"]["aggregates"]["count"] == 3


def test_llm_invented_satellite_name_falls_back(db, monkeypatch):
    fetched = fresh_catalog(db)
    stub_llm(monkeypatch,
             f"Catálogo CelesTrak descargado el {fetched.isoformat()[:10]}: 3 objetos.",
             ["SPACEMOBILE-999 lidera la constelación."])
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "determinista"
    assert "no contrastados" in result["note"]
    assert result["analysis"]["llm_interpretation"] is None


def test_llm_generic_summary_without_source_or_date_falls_back(db, monkeypatch):
    fresh_catalog(db)
    stub_llm(monkeypatch, "Resumen general del catálogo de satélites.")
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "determinista"
    assert "no contrastados" in result["note"]
    assert result["analysis"]["llm_interpretation"] is None


def test_quota_cap_falls_back_honestly(db, monkeypatch):
    fresh_catalog(db)
    monkeypatch.setenv("ASTS_LLM_ENABLED", "1")
    monkeypatch.setattr(service, "reserve_llm_call", lambda *_args: {
        "allowed": False, "minute_used": 2, "minute_limit": 2,
        "day_used": 30, "day_limit": 30, "reset": "UTC calendar minute/day"})
    result = service.analyze_asts_catalog(db)
    assert result["mode"] == "determinista"
    assert result["note"] == "Análisis LLM no disponible: tope alcanzado."


def test_llm_input_aggregated_for_large_catalog(db, monkeypatch):
    now = datetime.now(UTC)
    fetched = now - timedelta(hours=1)
    catalog = [row(60000 + i, f"SPACEMOBILE-{i:03d}", fetched - timedelta(minutes=i))
               for i in range(200)]
    persist_catalog(db, catalog, fetched)
    payload, mode = service._llm_payload(catalog, service._aggregates(catalog), fetched.isoformat())
    assert mode == "agregado"
    assert "agregados" in payload and "satelites" not in payload
    assert "No inventes filas" in payload


def test_quota_is_tenant_scoped_and_reports_limit(monkeypatch):
    class Config:
        is_production = False
        asts_llm_calls_per_minute = 1
        asts_llm_calls_per_day = 3

    config = Config()
    monkeypatch.setattr(quota, "_LOCAL", {})
    assert quota.reserve_llm_call("tenant-one", config)["allowed"] is True
    exceeded = quota.reserve_llm_call("tenant-one", config)
    assert exceeded["allowed"] is False and exceeded["minute_limit"] == 1
    assert quota.reserve_llm_call("tenant-two", config)["allowed"] is True
    with pytest.raises(RuntimeError):
        quota.reserve_llm_call(None, config)


def test_llm_request_pins_free_model_even_with_paid_override(monkeypatch):
    class Router:
        def resolve(self, request):
            return "paid-model-x"

    class Provider:
        name = "test"
        model_router = Router()

        async def complete(self, request):  # pragma: no cover - must never run
            raise AssertionError("should not call the paid model")

    monkeypatch.setattr(service, "create_llm_provider", lambda: Provider())
    with pytest.raises(RuntimeError, match="verified free model"):
        asyncio.run(service._analyze_with_llm("payload"))


def test_requires_tenant(db):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as session:
        with pytest.raises(ValueError, match="Tenant"):
            service.analyze_asts_catalog(session)
    engine.dispose()
