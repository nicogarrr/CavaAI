"""El embedder se carga una vez por proceso y el warmup es fail-open."""
import sys
import types

from app.services import hybrid_retrieval as hr


def _fake(monkeypatch, counter):
    module = types.ModuleType("fastembed")

    class FakeDense:
        def __init__(self, model):
            counter["n"] += 1

        def embed(self, texts):
            return [[0.1, 0.2] for _ in texts]

    module.TextEmbedding = FakeDense
    monkeypatch.setitem(sys.modules, "fastembed", module)


def test_dense_model_is_loaded_once_per_process(monkeypatch):
    counter = {"n": 0}
    _fake(monkeypatch, counter)
    hr.clear_model_cache()
    hr.embed_dense(["a"])
    hr.embed_dense(["b"])
    hr.embed_dense(["c"])
    assert counter["n"] == 1


def test_warm_models_loads_model_and_is_fail_open(monkeypatch):
    counter = {"n": 0}
    _fake(monkeypatch, counter)
    hr.clear_model_cache()
    assert hr.warm_models() is True
    hr.embed_dense(["x"])
    assert counter["n"] == 1
    monkeypatch.setitem(sys.modules, "fastembed", None)
    hr.clear_model_cache()
    assert hr.warm_models() is False
