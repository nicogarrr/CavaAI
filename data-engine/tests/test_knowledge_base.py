from modules.knowledge_base import KnowledgeBase


class FakeEmbeddingModel:
    def encode(self, values):
        class FakeVector(list):
            def tolist(self):
                return list(self)

        return [FakeVector([0.1, 0.2, 0.3]) for _ in values]


class FakeCollection:
    def __init__(self):
        self.last_query = None

    def query(self, **kwargs):
        self.last_query = kwargs
        return {
            "documents": [["AAPL specific", "MSFT specific", "General rule"]],
            "distances": [[0.1, 0.2, 0.3]],
            "metadatas": [[
                {"symbol": "AAPL"},
                {"symbol": "MSFT"},
                {},
            ]],
        }


def _kb_with_fake_collection():
    kb = KnowledgeBase.__new__(KnowledgeBase)
    kb._embedding_model = FakeEmbeddingModel()
    kb.collection = FakeCollection()
    return kb


def test_search_filters_by_symbol_in_chroma_where():
    kb = _kb_with_fake_collection()

    kb.search("apple", symbol="aapl")

    assert kb.collection.last_query["where"] == {"symbol": "AAPL"}


def test_general_only_excludes_symbol_specific_results():
    kb = _kb_with_fake_collection()

    results = kb.search("criterios inversión", n_results=5, general_only=True)

    assert [r["content"] for r in results] == ["General rule"]


def test_context_mixes_symbol_specific_and_general(monkeypatch):
    kb = _kb_with_fake_collection()
    calls = []

    def fake_search(query, n_results=10, collection_names=None, symbol=None, general_only=False):
        calls.append((query, symbol, general_only))
        if symbol == "AAPL":
            return [{"content": "AAPL moat", "metadata": {"symbol": "AAPL"}, "score": 0.9}]
        if general_only:
            return [{"content": "General ROIC rule", "metadata": {}, "score": 0.8}]
        return []

    monkeypatch.setattr(kb, "search", fake_search)

    context = kb.get_context_for_analysis("AAPL", "Apple")

    assert "AAPL moat" in context
    assert "General ROIC rule" in context
    assert any(call[1] == "AAPL" for call in calls)
    assert any(call[2] is True for call in calls)
