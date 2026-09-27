from app.services.research_assistant_narrative import _validated_sentences


def test_rejects_uncited_and_unattributed_claims():
    cites = [{"id": "news_event:1", "kind": "news_event", "excerpt": "344 satellites", "as_of": "2026-09-24"}]
    out = _validated_sentences({"sentences": [
        {"body": "La ITU aprobó 344 satélites.", "citation_ids": ["news_event:1"]},
        {"body": "Según un titular, 344 satélites.", "citation_ids": ["news_event:1"]},
        {"body": "Según un titular, 345 satélites.", "citation_ids": ["news_event:1"]},
        {"body": "Según un titular, 344 satélites.", "citation_ids": ["financial_fact:42"]},
    ]}, cites)
    assert len(out) == 1
    assert out[0]["body"] == "Según un titular, 344 satélites."
