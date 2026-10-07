"""Contract/production ingestion gates, synthetic and offline."""

import copy
import hashlib

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Company, Document, DocumentChunk, KnowledgeChunk, KnowledgeDocument, Tenant
from app.services.document_ingestion_service import DocumentIngestionService
from app.services.evidence_contract import (
    EvidenceSource,
    attach_translation,
    build_ingestion_evidence,
    category_for_type,
)
from app.services.knowledge_library_service import KnowledgeLibraryService


def fixture_source():
    return {
        "source_id": "filing-2025",
        "tenant_id": 1,
        "document_id": "filing-2025",
        "url": "https://example.invalid/filing-2025",
        "author": "Synthetic issuer",
        "published_on": "2026-02-01",
        "language": "en",
        "rights": "synthetic_fixture",
        "document_sha256": "33875bd674235075d19566150ee9cc5e921cec801a30dd23239241912952ebf6",
        "version": "fixture.1",
        "category": "filing",
        "review_status": "verified",
        "chunks": [
            {
                "chunk_id": "c0",
                "variants": [
                    {
                        "variant_id": "original",
                        "language": "en",
                        "text": "ACME reported FCF -12 USD million FY2025.",
                        "sha256": "33875bd674235075d19566150ee9cc5e921cec801a30dd23239241912952ebf6",
                    }
                ],
            }
        ],
        "reported_observations": [
            {
                "fact_id": "fcf-2025",
                "dimension": {
                    "entity": "ACME",
                    "metric": "fcf",
                    "period": "FY2025",
                    "unit": "USD_millions",
                    "currency": "USD",
                    "share_basis": "not_applicable",
                },
                "value": "-12",
                "citation": {
                    "source_id": "filing-2025",
                    "chunk_id": "c0",
                    "variant_id": "original",
                    "quote": "ACME reported FCF -12 USD million FY2025.",
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("source_type", "category"),
    [
        ("SEC", "filing"),
        ("primary_official", "filing"),
        ("news", "news_assertion"),
        ("article", "news_assertion"),
        ("fund_letter", "methodology"),
        ("book", "methodology"),
        ("personal_note", "user_contribution"),
        ("IR", "unclassified"),
    ],
)
def test_ingestion_category_is_not_verification(source_type, category):
    assert category_for_type(source_type) == category


def test_reported_observation_requires_number_in_original_quote():
    payload = fixture_source()
    payload["reported_observations"][0]["value"] = "999"
    with pytest.raises(ValidationError, match="reported_value_not_in_quote"):
        EvidenceSource.model_validate(payload)


@pytest.mark.parametrize("change", ["hash", "review", "category", "period"])
def test_source_fails_closed(change):
    payload = fixture_source()
    if change == "hash":
        payload["chunks"][0]["variants"][0]["sha256"] = "0" * 64
    elif change == "review":
        payload["review_status"] = "unreviewed"
    elif change == "category":
        payload["category"] = "methodology"
    else:
        payload["reported_observations"][0]["dimension"]["period"] = ""
    with pytest.raises(ValidationError):
        EvidenceSource.model_validate(payload)


def test_translation_is_one_source_and_preserves_original_observation():
    original = EvidenceSource.model_validate(fixture_source())
    translated = attach_translation(
        original,
        chunk_id="c0",
        tenant_id=1,
        variant_id="es-translation",
        language="es",
        text="FCF reportado -12.",
    )
    assert translated.source_id == original.source_id
    assert translated.document_sha256 == original.document_sha256
    assert translated.reported_observations == original.reported_observations
    assert len(translated.chunks) == 1
    assert len(translated.chunks[0].variants) == 2
    assert translated.chunks[0].variants[1].translation_of == "original"
    # Never allow translated digits to substitute the original fact citation.
    payload = translated.model_dump()
    payload["reported_observations"][0]["citation"]["variant_id"] = "es-translation"
    payload["reported_observations"][0]["citation"]["quote"] = "FCF reportado -12."
    with pytest.raises(ValidationError, match="reported_requires_original"):
        EvidenceSource.model_validate(payload)


def test_cross_tenant_translation_and_duplicate_variant_rejected():
    source = EvidenceSource.model_validate(fixture_source())
    with pytest.raises(ValueError, match="cross_tenant_translation"):
        attach_translation(source, chunk_id="c0", tenant_id=2, variant_id="es", language="es", text="Hola")
    with pytest.raises(ValueError, match="duplicate_variant"):
        attach_translation(
            source, chunk_id="c0", tenant_id=1, variant_id="original", language="es", text="Hola"
        )


def test_unknown_date_rights_and_tenant_not_fabricated():
    args = dict(
        document_id="document:1",
        checksum="a" * 64,
        source_type="SEC",
        chunks=[{"text": "Original text", "metadata": {}}],
    )
    assert build_ingestion_evidence(tenant_id=None, **args)["status"] == "tenant_unbound"
    result = build_ingestion_evidence(tenant_id=1, **args)
    assert result["published_on"] is None
    assert result["rights"] == "unknown"
    assert result["language"] == "und"
    assert result["review_status"] == "unreviewed"
    assert result["reported_observations"] == []


def test_parser_page_section_and_truncation_preserved():
    ledger = build_ingestion_evidence(
        tenant_id=1,
        document_id="document:1",
        checksum="a" * 64,
        source_type="filing",
        chunks=[
            {
                "text": "Truncated table",
                "metadata": {
                    "section_title": "Cash flow",
                    "block_metadata": [{"page": 5, "truncated": True}],
                },
            }
        ],
    )
    assert ledger["chunks"][0]["page"] == 5
    assert ledger["chunks"][0]["section"] == "Cash flow"
    assert ledger["chunks"][0]["complete"] is False


def test_real_ingestion_persists_ledger_and_chunk_links(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAVAAI_ENABLE_AUTO_KPI_EXTRACTION", "0")
    monkeypatch.setenv("CAVAAI_ENABLE_VECTOR_INGEST", "0")
    monkeypatch.setenv("LLM_ENABLED", "false")
    # No model classification or remote call in this gate.
    monkeypatch.setattr(DocumentIngestionService, "_jev_doc_type_meta", lambda self, text: {})
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    content = b"A durable moat requires evidence and disciplined capital allocation."
    checksum = hashlib.sha256(content).hexdigest()
    with Session(engine) as db:
        tenant = Tenant(external_id="evidence-test")
        db.add(tenant)
        db.flush()
        db.info["tenant_id"] = tenant.id
        db.add(
            Company(
                ticker="EVID",
                name="Synthetic company",
                exchange="TEST",
                company_type="operating",
                valuation_model="dcf",
            )
        )
        db.commit()
        imported = DocumentIngestionService().ingest_bytes(
            db,
            ticker="EVID",
            title="Synthetic source",
            content=content,
            filename="source.txt",
            source_type="news",
        )
        document = db.get(Document, imported["document_id"])
        source = EvidenceSource.model_validate(document.metadata_["evidence_contract"])
        assert source.category == "news_assertion"
        assert source.document_sha256 == checksum
        assert source.published_on is None  # existing document fetched-at is NOT publication
        chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == document.id))
        assert chunk.metadata_["evidence_source_id"] == source.source_id
        assert chunk.metadata_["evidence_chunk_id"] == source.chunks[0].chunk_id
        assert source.chunks[0].variants[0].text == chunk.text
        duplicate = DocumentIngestionService().ingest_bytes(
            db,
            ticker="EVID",
            title="Same source",
            content=content,
            filename="source.txt",
            source_type="news",
        )
        assert duplicate["status"] == "duplicate"
        knowledge = KnowledgeLibraryService().ingest_bytes(
            db,
            title="Methodology",
            content=content,
            filename="letter.txt",
            document_type="fund_letter",
            author="Synthetic author",
            language="en",
        )
        document = db.get(KnowledgeDocument, knowledge["knowledge_document_id"])
        source = EvidenceSource.model_validate(document.metadata_["evidence_contract"])
        assert source.category == "methodology"
        assert source.author == "Synthetic author"
        assert not source.reported_observations
        chunk = db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.knowledge_document_id == document.id))
        assert chunk.metadata_["evidence_chunk_id"] == source.chunks[0].chunk_id
        assert source.chunks[0].variants[0].text == chunk.content
    engine.dispose()


def test_registry_rejects_translation_as_second_source():
    from app.services.evidence_contract import EvidenceRegistry

    source = EvidenceSource.model_validate(fixture_source())
    translated = attach_translation(
        source, chunk_id="c0", tenant_id=1, variant_id="es", language="es", text="Hola"
    )
    with pytest.raises(ValueError, match="duplicate_source"):
        EvidenceRegistry(1, (source, translated))


def test_duplicate_fact_and_chunk_ids_rejected():
    for field in ("chunks", "reported_observations"):
        payload = fixture_source()
        payload[field].append(copy.deepcopy(payload[field][0]))
        with pytest.raises(ValidationError, match="duplicate_"):
            EvidenceSource.model_validate(payload)
