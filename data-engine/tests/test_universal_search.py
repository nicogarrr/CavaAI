from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import (
    Claim,
    Company,
    DecisionLesson,
    Document,
    DocumentChunk,
    FinancialFact,
    InvestmentPrinciple,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    Tenant,
)
from app.services.universal_search_service import UniversalSearchService


def test_universal_search_fuses_corpora_and_applies_metadata_filters():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="search-test", name="Search test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = Company(
            ticker="SRCH",
            name="Search Co",
            exchange="TEST",
            currency="USD",
            sector="Industrials",
            industry="Test",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        filing = Document(
            company_id=company.id,
            title="2025 annual filing",
            source_type="sec_filing",
            source_url="https://www.sec.gov/example",
        )
        db.add(filing)
        db.flush()
        db.add(
            DocumentChunk(
                document_id=filing.id,
                chunk_index=0,
                text="Capital allocation discipline prioritized reinvestment and buybacks.",
            )
        )
        db.add_all(
            [
                FinancialFact(
                    company_id=company.id,
                    metric="return_on_invested_capital",
                    value=Decimal("0.18"),
                    unit="decimal",
                    period="FY2025",
                    fiscal_year=2025,
                    source_id=filing.id,
                    source_type="sec_filing",
                    confidence=Decimal("0.95"),
                ),
                Claim(
                    company_id=company.id,
                    statement="Management has demonstrated disciplined capital allocation.",
                    status="verified",
                    confidence=Decimal("0.8"),
                ),
                DecisionLesson(
                    company_id=company.id,
                    taxonomy="valuation_anchoring",
                    lesson="Capital allocation quality must be assessed before valuation.",
                    status="approved",
                ),
            ]
        )
        collection = KnowledgeCollection(
            name="Capital Allocation",
            slug="capital-allocation",
            collection_type="default",
        )
        db.add(collection)
        db.flush()
        knowledge_document = KnowledgeDocument(
            collection_id=collection.id,
            title="Owner earnings letter",
            author="Investor",
            document_type="fund_letter",
            status="ready",
        )
        db.add(knowledge_document)
        db.flush()
        knowledge_chunk = KnowledgeChunk(
            knowledge_document_id=knowledge_document.id,
            chunk_index=0,
            content="Capital allocation is the test of management discipline.",
            source_locator={"page": 4},
        )
        db.add(knowledge_chunk)
        db.flush()
        db.add(
            InvestmentPrinciple(
                knowledge_document_id=knowledge_document.id,
                knowledge_chunk_id=knowledge_chunk.id,
                collection_id=collection.id,
                principle="Judge managers by capital allocation discipline.",
                principle_fingerprint="b" * 64,
                category="capital_allocation",
                exact_fragment="Capital allocation is the test of management discipline.",
                author="Investor",
                confidence=Decimal("0.9"),
                status="approved",
                applies_to_company_ids=[company.id],
            )
        )
        db.commit()

        response = UniversalSearchService().search(db, "capital allocation discipline", include_vector=False)

        types = {row["entity_type"] for row in response["results"]}
        assert {
            "document_chunk",
            "claim",
            "decision_lesson",
            "knowledge_chunk",
            "investment_principle",
        }.issubset(types)
        assert response["retrieval"]["fusion"] == "reciprocal_rank_fusion"
        assert response["retrieval"]["lexical_backend"] == "portable_lexical_fallback"
        assert all(row["citation"] for row in response["results"])
        assert response["results"][0]["source_tier"] == "tier_1_regulatory"

        collection_only = UniversalSearchService().search(
            db,
            "capital allocation",
            collection_id=collection.id,
            include_vector=False,
        )
        assert collection_only["results"]
        assert {row["entity_type"] for row in collection_only["results"]} <= {
            "knowledge_chunk",
            "investment_principle",
            "investment_case",
        }
        assert all(row["collection_id"] == collection.id for row in collection_only["results"])


def test_vector_only_hit_is_hydrated_when_fts_returns_no_candidate(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        tenant = Tenant(external_id="vector-only", name="Vector only")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        company = Company(
            ticker="VCTR",
            name="Vector Co",
            exchange="TEST",
            currency="USD",
            sector="Technology",
            industry="Software",
            company_type="standard",
            valuation_model="standard_dcf",
            special_sources=[],
            special_risks=[],
            factor_tags=[],
        )
        db.add(company)
        db.flush()
        document = Document(
            company_id=company.id,
            title="Product architecture",
            source_type="company_ir",
            source_url="https://ir.example.test/architecture",
        )
        db.add(document)
        db.flush()
        chunk = DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            text="The platform uses a proprietary distributed data plane.",
        )
        db.add(chunk)
        db.commit()

        service = UniversalSearchService()
        monkeypatch.setenv("CAVAAI_ENABLE_VECTOR_SEARCH", "1")
        monkeypatch.setattr(service, "_candidates", lambda *args, **kwargs: [])

        from app.services.rag import RAGIndex

        monkeypatch.setattr(
            RAGIndex,
            "search",
            lambda *args, **kwargs: [
                {
                    "entity_type": "document_chunk",
                    "entity_id": chunk.id,
                    "score": 0.91,
                }
            ],
        )

        response = service.search(
            db,
            "semantic systems moat",
            ticker="VCTR",
        )

        assert response["total"] == 1
        assert response["results"][0]["entity_id"] == chunk.id
        assert response["results"][0]["scores"]["lexical"] == 0
        assert response["results"][0]["scores"]["vector"] == 0.91
