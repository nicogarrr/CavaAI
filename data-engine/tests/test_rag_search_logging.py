import logging

from app.services.rag import RAGIndex


def test_search_logs_cause_when_embedder_fails(monkeypatch, caplog):
    index = RAGIndex()

    def boom():
        raise PermissionError("[Errno 13] Permission denied: '/home/cavaai'")

    monkeypatch.setattr(index, "_embedder", boom)
    with caplog.at_level(logging.WARNING, logger="app.services.rag"):
        assert index.search("q", ticker="ASTS", tenant_id=1) == []
    assert any("PermissionError" in r.getMessage() for r in caplog.records)


def test_search_without_tenant_returns_empty_without_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.rag"):
        assert RAGIndex().search("q", ticker="ASTS", tenant_id=None) == []
    assert not caplog.records
