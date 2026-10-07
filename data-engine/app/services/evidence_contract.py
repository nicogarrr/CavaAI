"""Versioned evidence boundary. Source text is data, never executable authority.

Additive phase 1: no valuation/publication guard is relaxed by this module.
Unknown metadata stays unknown. A source type alone never verifies a number.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "evidence.v1"
SourceCategory = Literal["filing", "news_assertion", "methodology", "user_contribution", "unclassified"]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextVariant(ContractModel):
    variant_id: str = Field(min_length=1)
    language: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    translation_of: str | None = None

    @model_validator(mode="after")
    def verify_hash(self) -> Self:
        if hashlib.sha256(self.text.encode()).hexdigest() != self.sha256:
            raise ValueError("variant_hash_mismatch")
        return self


class EvidenceChunk(ContractModel):
    chunk_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    complete: bool = True
    variants: tuple[TextVariant, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def verify_variants(self) -> Self:
        ids = [item.variant_id for item in self.variants]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate_variant")
        originals = [item for item in self.variants if item.translation_of is None]
        if len(originals) != 1:
            raise ValueError("one_original_required")
        if any(item.translation_of not in (None, originals[0].variant_id) for item in self.variants):
            raise ValueError("translation_original_missing")
        return self


class Citation(ContractModel):
    source_id: str
    chunk_id: str
    variant_id: str
    quote: str = Field(min_length=1)


class FinancialDimension(ContractModel):
    entity: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    period: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    share_basis: str = Field(min_length=1)  # ordinary, ADR, not_applicable, etc.


class ReportedObservation(ContractModel):
    fact_id: str = Field(min_length=1)
    dimension: FinancialDimension
    value: Decimal = Field(allow_inf_nan=False)
    citation: Citation

    @model_validator(mode="after")
    def require_literal_value(self) -> Self:
        # Contract v1 accepts explicit unscaled decimal literals only. Locale
        # conversion/scaling requires a separately verified adapter, not a guess.
        numbers = re.findall(r"(?<![\w.,])[-+]?\d+(?:\.\d+)?(?!\w|[.,]\d)", self.citation.quote)
        if self.value not in {Decimal(number) for number in numbers}:
            raise ValueError("reported_value_not_in_quote")
        return self


class EvidenceSource(ContractModel):
    contract_version: Literal["evidence.v1"] = CONTRACT_VERSION
    source_id: str = Field(min_length=1)
    tenant_id: int = Field(ge=1)
    document_id: str = Field(min_length=1)
    url: str | None = None
    author: str | None = None
    published_on: date | None = None
    language: str = Field(min_length=1)
    rights: str = "unknown"  # public access is not a licence to redistribute
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    version: str = Field(min_length=1)
    category: SourceCategory
    review_status: Literal["unreviewed", "verified", "rejected"] = "unreviewed"
    chunks: tuple[EvidenceChunk, ...] = ()
    reported_observations: tuple[ReportedObservation, ...] = ()

    @model_validator(mode="after")
    def verify_observations(self) -> Self:
        ids = [chunk.chunk_id for chunk in self.chunks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate_chunk")
        fact_ids = [fact.fact_id for fact in self.reported_observations]
        if len(set(fact_ids)) != len(fact_ids):
            raise ValueError("duplicate_fact")
        if self.reported_observations and (self.category != "filing" or self.review_status != "verified"):
            raise ValueError("reported_requires_verified_filing")
        for fact in self.reported_observations:
            validate_citation(fact.citation, self, original_required=True)
        return self


def validate_citation(citation: Citation, source: EvidenceSource, *, original_required: bool = False) -> None:
    if citation.source_id != source.source_id:
        raise ValueError("citation_source_mismatch")
    chunk = next((item for item in source.chunks if item.chunk_id == citation.chunk_id), None)
    if chunk is None:
        raise ValueError("citation_chunk_missing")
    if not chunk.complete:
        raise ValueError("citation_chunk_incomplete")
    variant = next((item for item in chunk.variants if item.variant_id == citation.variant_id), None)
    if variant is None:
        raise ValueError("citation_variant_missing")
    if original_required and variant.translation_of is not None:
        raise ValueError("reported_requires_original")
    if citation.quote not in variant.text:
        raise ValueError("citation_quote_mismatch")


class EvidenceRegistry:
    """Explicit tenant boundary even when SQL/RAG callers already filter."""

    def __init__(self, tenant_id: int, sources: tuple[EvidenceSource, ...]):
        if tenant_id < 1:
            raise ValueError("tenant_required")
        self.tenant_id = tenant_id
        self.sources: dict[str, EvidenceSource] = {}
        for source in sources:
            if source.tenant_id != tenant_id:
                raise ValueError("cross_tenant_source")
            if source.source_id in self.sources:
                raise ValueError("duplicate_source_use_variants_not_translation_sources")
            self.sources[source.source_id] = source

    def resolve(self, citation: Citation) -> EvidenceSource:
        source = self.sources.get(citation.source_id)
        if source is None:
            raise ValueError("citation_source_missing")
        if source.review_status == "rejected":
            raise ValueError("citation_source_rejected")
        validate_citation(citation, source)
        return source


class EvidenceClaim(ContractModel):
    """Structured eval candidate, not a permission to publish a thesis.

    Reported values must match a verified observation exactly; inferred ranges
    live in scenario scope, never in the factual slot occupied by real data.
    """

    kind: Literal["reported", "derived", "inference", "assumption", "unknown"]
    text: str = Field(min_length=1)
    scope: Literal["factual", "exploratory", "scenario"]
    dimension: FinancialDimension | None = None
    value: Decimal | None = Field(default=None, allow_inf_nan=False)
    value_range: tuple[Decimal, Decimal] | None = None
    citations: tuple[Citation, ...] = ()
    fact_id: str | None = None
    method: str | None = None
    refuted_by: str | None = None
    confidence: Literal["no calibrada"] = "no calibrada"


def validate_claim(claim: EvidenceClaim, registry: EvidenceRegistry) -> None:
    sources = [registry.resolve(citation) for citation in claim.citations]
    if claim.value_range is not None:
        low, high = claim.value_range
        if not low.is_finite() or not high.is_finite() or low > high:
            raise ValueError("invalid_range")
    if claim.value is not None and claim.value_range is not None:
        raise ValueError("value_and_range_are_exclusive")
    if (claim.value is not None or claim.value_range is not None) and claim.dimension is None:
        raise ValueError("numeric_dimension_required")
    if claim.kind == "unknown":
        if claim.value is not None or claim.value_range is not None:
            raise ValueError("unknown_has_value")
        return
    if claim.kind == "reported":
        if claim.scope != "factual" or claim.value is None or claim.fact_id is None or not sources:
            raise ValueError("reported_requires_observation")
        if claim.value_range is not None:
            raise ValueError("reported_is_not_range")
        values = {
            fact.value
            for source in registry.sources.values()
            for fact in source.reported_observations
            if fact.dimension == claim.dimension
        }
        if len(values) > 1:
            raise ValueError("conflicting_reported_observations")
        for source, citation in zip(sources, claim.citations, strict=True):
            fact = next(
                (item for item in source.reported_observations if item.fact_id == claim.fact_id), None
            )
            if (
                fact is not None
                and fact.value == claim.value
                and fact.dimension == claim.dimension
                and fact.citation == citation
            ):
                return
        raise ValueError("reported_observation_mismatch")
    if not claim.method:
        raise ValueError("non_reported_method_required")
    if claim.kind == "derived":
        # Phase 1 has no formula executor yet. Do not pretend to verify arithmetic.
        raise ValueError("derived_executor_not_available")
    if claim.scope == "factual":
        raise ValueError("inference_is_not_factual")
    if claim.fact_id is not None:
        raise ValueError("inference_cannot_claim_reported_fact_id")
    if not claim.refuted_by:
        raise ValueError("exploration_refutation_required")
    if claim.dimension is not None and claim.scope != "scenario":
        for source in registry.sources.values():
            if any(fact.dimension == claim.dimension for fact in source.reported_observations):
                raise ValueError("real_observation_cannot_be_replaced")
    if claim.kind == "inference" and not sources:
        raise ValueError("inference_evidence_required")


def category_for_type(source_type: str) -> SourceCategory:
    """Conservative semantic routing, NOT verification of authorship or facts."""
    kind = source_type.strip().lower()
    if kind in {"sec", "sec_10k", "sec_10q", "esef", "filing", "primary_official"}:
        return "filing"
    if kind in {"news", "article", "news_article", "rss", "gdelt"}:
        return "news_assertion"
    if kind in {"fund_letter", "book", "paper", "principle", "historical_case"}:
        return "methodology"
    if kind in {"manual", "personal_note", "personal_postmortem", "user", "user_note"}:
        return "user_contribution"
    return "unclassified"


def build_ingestion_evidence(
    *,
    tenant_id: int | None,
    document_id: str,
    checksum: str,
    source_type: str,
    chunks: list[dict],
    url: str | None = None,
    author: str | None = None,
    published_on: date | None = None,
    language: str = "und",
) -> dict:
    """Persist one ledger per document in existing JSON metadata, no migration.

    Legacy anonymous test imports retain an explicit unbound state; production
    sessions provide tenant_id. They cannot enter a registry until rebound.
    This does not extract/review financial observations, or infer dates/rights.
    """
    if tenant_id is None:
        return {"contract_version": CONTRACT_VERSION, "status": "tenant_unbound"}
    source_id = f"tenant:{tenant_id}:{document_id}:{checksum}"
    evidence_chunks = []
    for index, item in enumerate(chunks):
        text = item["text"]
        block_meta = item.get("metadata", {}).get("block_metadata") or []
        page = next(
            (
                block.get("page")
                for block in block_meta
                if isinstance(block, dict) and isinstance(block.get("page"), int) and block["page"] > 0
            ),
            None,
        )
        # Parser warnings don't establish table completeness. Do not invent it.
        complete = not any(
            isinstance(block, dict) and (block.get("truncated") or block.get("incomplete"))
            for block in block_meta
        )
        evidence_chunks.append(
            EvidenceChunk(
                chunk_id=f"{source_id}:chunk:{index}",
                page=page,
                section=item.get("metadata", {}).get("section_title"),
                complete=complete,
                variants=(
                    TextVariant(
                        variant_id="original",
                        language=language,
                        text=text,
                        sha256=hashlib.sha256(text.encode()).hexdigest(),
                    ),
                ),
            )
        )
    source = EvidenceSource(
        source_id=source_id,
        tenant_id=tenant_id,
        document_id=document_id,
        url=url,
        author=author,
        published_on=published_on,
        language=language,
        document_sha256=checksum,
        version=checksum,
        category=category_for_type(source_type),
        chunks=tuple(evidence_chunks),
    )
    return source.model_dump(mode="json")


def attach_translation(
    source: EvidenceSource, *, chunk_id: str, tenant_id: int, variant_id: str, language: str, text: str
) -> EvidenceSource:
    """A translation is a variant under the SAME source/chunk ID, never a vote."""
    if tenant_id != source.tenant_id:
        raise ValueError("cross_tenant_translation")
    if not any(chunk.chunk_id == chunk_id for chunk in source.chunks):
        raise ValueError("translation_chunk_missing")
    chunks = []
    for chunk in source.chunks:
        if chunk.chunk_id == chunk_id:
            original = next(item for item in chunk.variants if item.translation_of is None)
            translated = TextVariant(
                variant_id=variant_id,
                language=language,
                text=text,
                sha256=hashlib.sha256(text.encode()).hexdigest(),
                translation_of=original.variant_id,
            )
            chunk = EvidenceChunk.model_validate(
                {**chunk.model_dump(), "variants": (*chunk.variants, translated)}
            )
        chunks.append(chunk)
    return EvidenceSource.model_validate({**source.model_dump(), "chunks": tuple(chunks)})
