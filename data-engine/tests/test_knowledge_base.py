from modules.vector_store import QdrantVectorStore


class FakeEmbeddingModel:
    def encode(self, values):
        class FakeVector(list):
            def tolist(self):
                return list(self)

        return [FakeVector([0.1, 0.2, 0.3]) for _ in values]


class FakeHit:
    def __init__(self, content, score, metadata):
        self.payload = {"content": content, **metadata}
        self.score = score


class FakeClient:
    def __init__(self):
        self.last_search = None

    def search(self, **kwargs):
        self.last_search = kwargs
        return [
            FakeHit("AAPL specific", 0.9, {"symbol": "AAPL"}),
            FakeHit("MSFT specific", 0.8, {"symbol": "MSFT"}),
            FakeHit("General rule", 0.7, {}),
        ]


def _store_with_fake_client():
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.collection_name = "knowledge"
    store.embedding_model = FakeEmbeddingModel()
    store.client = FakeClient()
    return store


def test_search_filters_by_symbol_in_qdrant_filter():
    store = _store_with_fake_client()

    store.search("apple", symbol="aapl")

    assert store.client.last_search["query_filter"] is not None
    assert "AAPL" in repr(store.client.last_search["query_filter"])


def test_general_only_excludes_symbol_specific_results():
    store = _store_with_fake_client()

    results = store.search("criterios inversion", n_results=5, general_only=True)

    assert [r["content"] for r in results] == ["General rule"]


def test_context_mixes_symbol_specific_and_general(monkeypatch):
    store = _store_with_fake_client()
    calls = []

    def fake_search(query, n_results=10, collection_names=None, symbol=None, general_only=False):
        calls.append((query, symbol, general_only))
        if symbol == "AAPL":
            return [{"content": "AAPL moat", "metadata": {"symbol": "AAPL"}, "score": 0.9}]
        if general_only:
            return [{"content": "General ROIC rule", "metadata": {}, "score": 0.8}]
        return []

    monkeypatch.setattr(store, "search", fake_search)

    context = store.get_context_for_analysis("AAPL", "Apple")

    assert "AAPL moat" in context
    assert "General ROIC rule" in context
    assert any(call[1] == "AAPL" for call in calls)
    assert any(call[2] is True for call in calls)
