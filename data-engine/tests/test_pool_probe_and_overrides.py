import logging

from sqlalchemy import create_engine, text

from app.core import pool_probe
from app.core.config import Settings


def test_empty_model_overrides_env_is_an_empty_dict(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_OVERRIDES", "")
    assert Settings(_env_file=None).llm_model_overrides == {}


def test_json_model_overrides_env_still_parses(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_OVERRIDES", '{"a": "b"}')
    assert Settings(_env_file=None).llm_model_overrides == {"a": "b"}


def test_pool_probe_reports_outstanding_connections(monkeypatch, caplog, tmp_path):
    monkeypatch.setattr(pool_probe, "_INSTALLED", False)
    monkeypatch.setattr(pool_probe, "_OUT", {})
    monkeypatch.setattr(pool_probe, "_LAST_DUMP", 0.0)
    engine = create_engine(f"sqlite:///{tmp_path}/p.db", connect_args={"check_same_thread": False})
    pool_probe.install(engine, threshold=2, min_interval_s=0)
    held = [engine.connect(), engine.connect()]
    with caplog.at_level(logging.WARNING, logger=pool_probe.logger.name):
        held.append(engine.connect())
    assert any("db pool pressure" in r.getMessage() for r in caplog.records)
    message = " ".join(r.getMessage() for r in caplog.records)
    assert "SELECT" not in message
    assert len(pool_probe.outstanding()) == 3
    for conn in held:
        conn.execute(text("select 1"))
        conn.close()
    assert pool_probe.outstanding() == []
