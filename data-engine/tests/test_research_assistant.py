from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.routes.research_assistant import AssistantRequest, AssistantResponse
from app.models.entities import Base, Company, Document, FinancialFact, NewsEvent, ResearchReview, Tenant
from app.services.research_assistant_service import answer, guide_context


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def setup(db):
    a = Tenant(external_id="assistant-a", name="A", status="active", metadata_={})
    b = Tenant(external_id="assistant-b", name="B", status="active", metadata_={})
    company = Company(ticker="ASTS", name="AST SpaceMobile", exchange="NASDAQ", currency="USD",
                      company_type="holding", valuation_model="unassigned")
    db.add_all((a, b, company))
    db.flush()
    db.info["tenant_id"] = a.id
    return a, b, company


def test_contract_no_data_and_no_writeback(db):
    a, b, company = setup(db)
    before = db.query(ResearchReview).count()
    response = AssistantResponse.model_validate(answer(db, AssistantRequest(
        mode="explore", question="remember this idea", ticker="ASTS")))
    assert response.status == "insufficient_data"
    assert response.citations == [] and response.writeback is False
    assert db.query(ResearchReview).count() == before
    with pytest.raises(ValueError):
        AssistantRequest(mode="guide", question="What now?")


def test_tenant_isolation_ticket_binding_and_cited_rows(db):
    a, b, company = setup(db)
    doc = Document(tenant_id=a.id, company_id=company.id, title="Company filing",
                   source_type="company_ir", source_url="https://example.com/filing")
    other_doc = Document(tenant_id=b.id, company_id=company.id, title="Other's filing",
                         source_type="company_ir", source_url="https://example.com/private")
    db.add(doc)
    db.flush()
    db.info["tenant_id"] = b.id
    db.add(other_doc)
    db.flush()
    db.info["tenant_id"] = a.id
    db.add(FinancialFact(tenant_id=a.id, company_id=company.id, metric="revenue",
                         value=Decimal("123"), unit="USD", period="FY2025", fiscal_year=2025,
                         source_id=doc.id, source_type="company_ir"))

    db.add(NewsEvent(tenant_id=a.id, company_id=company.id, title="ASTS ITU filing reported",
                     source="Publisher", url="https://example.com/article",
                     date=datetime(2026, 9, 24, tzinfo=UTC), metadata_={"date_source": "gdelt_first_seen"}))

    review = ResearchReview(tenant_id=a.id, company_id=company.id, review_type="news", title="Review ITU",
                            summary="Check original ITU filing", status="open")
    other_review = ResearchReview(tenant_id=b.id, company_id=company.id, review_type="news", title="Private",
                                  summary="Private review", status="open")
    db.add(review)
    db.commit()
    db.info["tenant_id"] = b.id
    db.add(FinancialFact(tenant_id=b.id, company_id=company.id, metric="revenue",
                         value=Decimal("999"), unit="USD", period="FY2025", fiscal_year=2025,
                         source_id=other_doc.id, source_type="company_ir"))
    db.add(NewsEvent(tenant_id=b.id, company_id=company.id, title="Private news",
                     source="Other", url="https://example.com/private-news",
                     date=datetime(2026, 9, 24, tzinfo=UTC), metadata_={"date_source": "source"}))
    db.add(other_review)
    db.commit()
    db.info["tenant_id"] = a.id
    response = AssistantResponse.model_validate(answer(db, AssistantRequest(
        mode="guide", question="What does the ITU filing say?", ticker="ASTS", review_id=review.id)))
    assert response.review_id == review.id and response.writeback is False
    assert response.status == "answered"
    assert any(c.kind == "news_event" for c in response.citations)
    assert all(c.kind != "financial_fact" for c in response.citations)
    assert "999" not in response.answer and "Private" not in response.answer
    assert all(cid in {c.id for c in response.citations} for sec in response.sections for cid in sec.citation_ids)
    context = guide_context(db, "ASTS")
    assert context["review_id"] == review.id
    assert [r["id"] for r in context["open_reviews"]] == [review.id]
    with pytest.raises(LookupError):
        answer(db, AssistantRequest(mode="guide", question="What now?", ticker="ASTS", review_id=other_review.id))


def test_relevant_filing_chunk_beats_six_unrelated_facts(db):
    from app.models.entities import DocumentChunk

    tenant, _, company = setup(db)
    for i in range(6):
        doc = Document(tenant_id=tenant.id, company_id=company.id, title=f"Annual revenue {i}",
                       source_type="company_ir", source_url=f"https://example.com/revenue/{i}")
        db.add(doc)
        db.flush()
        db.add(FinancialFact(tenant_id=tenant.id, company_id=company.id, metric="revenue",
                             value=Decimal(str(i + 10)), unit="USD", period="FY2025", fiscal_year=2025,
                             source_id=doc.id, source_type="company_ir"))
    filing = Document(tenant_id=tenant.id, company_id=company.id, title="D-BLUEBIRD ITU filing",
                      source_type="regulatory", source_url="https://example.com/itu-filing",
                      published_at=datetime(2026, 9, 24, tzinfo=UTC))
    db.add(filing)
    db.flush()
    db.add(DocumentChunk(tenant_id=tenant.id, document_id=filing.id, chunk_index=0,
                         text="ITU filing D-BLUEBIRD describes the constellation registration.", token_count=10))
    db.commit()
    response = AssistantResponse.model_validate(answer(db, AssistantRequest(
        mode="guide", ticker="ASTS", question="¿Qué dice el filing ITU D-BLUEBIRD?")))
    assert response.status == "answered"
    assert any(c.kind == "document_chunk" and "ITU" in c.source for c in response.citations)
    assert all(c.kind != "financial_fact" for c in response.citations)
    missing = AssistantResponse.model_validate(answer(db, AssistantRequest(
        mode="explore", ticker="ASTS", question="¿Qué pasó con el propulsor xenón?")))
    assert missing.status == "insufficient_data"
    assert missing.citations == [] and missing.missing_data
