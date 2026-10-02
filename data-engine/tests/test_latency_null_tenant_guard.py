"""El volcado de latencia de trafico publico (sin tenant) no puede romperse
con la auth obligatoria, que es el caso de produccion."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.database import Base
from app.metrics import config, latency
from app.models.metrics import ApiLatencyWindow
from tests.test_backend_metrics_latency import _observation


def test_trafico_publico_sin_tenant_se_guarda_con_auth_obligatoria(monkeypatch):
    monkeypatch.setattr(database.settings, "research_auth_required", True)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    recorder = latency.LatencyRecorder(window_size=config.WINDOW_HOUR, flush_max_series=10_000)
    recorder.record(_observation(None, route="/api/health"))
    recorder.record(_observation(None, route="/api/health"))
    assert recorder.flush(session) == 1
    rows = list(session.scalars(select(ApiLatencyWindow)).all())
    assert len(rows) == 1
    assert rows[0].tenant_id is None
    assert rows[0].request_count == 2
    # segundo volcado: suma sobre la fila existente, no duplica
    recorder.record(_observation(None, route="/api/health"))
    assert recorder.flush(session) == 1
    rows = list(session.scalars(select(ApiLatencyWindow)).all())
    assert len(rows) == 1 and rows[0].request_count == 3
