from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import math
import re

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    Document,
    DocumentChunk,
    EvidenceSuggestion,
    ThesisChange,
)
from app.services.review_alert_service import ReviewAlertService
from app.services.source_hierarchy_service import classify_source


STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "being",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "most",
    "over",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "were",
    "which",
    "with",
    "would",
    "para",
    "como",
    "esta",
    "este",
    "entre",
    "desde",
    "sobre",
    "tambien",
    "tiene",
}
NEGATIONS = {
    "no",
    "not",
    "never",
    "without",
    "cannot",
    "won't",
    "didn't",
    "isn't",
    "decreased",
    "declined",
    "missed",
    "cancelled",
    "terminated",
    "lowered",
    "cut",
}
SUPERSESSION_MARKERS = {
    "revised",
    "updated",
    "raised guidance",
    "lowered guidance",
    "no longer",
    "replaced",
    "supersedes",
    "now expects",
    "previously expected",
}
MATERIAL_TERMS = {
    "revenue",
    "guidance",
    "margin",
    "cash",
    "debt",
    "dilution",
    "offering",
    "contract",
    "customer",
    "launch",
    "approval",
    "regulatory",
    "risk",
    "expects",
    "forecast",
    "profit",
    "loss",
    "capital",
    "buyback",
    "partnership",
    "earnings",
}


@dataclass(frozen=True)
class ExtractedStatement:
    text: str
    confidence: float
    materiality_score: int
    quote: str


@dataclass(frozen=True)
class ClaimMatch:
    claim: Claim
    similarity: float


@dataclass(frozen=True)
class RelationClassification:
    relation: str
    confidence: float
    rationale: str


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9\-']+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / math.sqrt(
        len(left_tokens) * len(right_tokens)
    )


def _numbers(text: str) -> list[float]:
    values: list[float] = []
    for raw in re.findall(r"(?<!\w)-?\d+(?:\.\d+)?", text.replace(",", "")):
        try:
            values.append(float(raw))
        except ValueError:
            continue
    return values


def _numeric_conflict(old: str, new: str) -> bool:
    old_values = _numbers(old)
    new_values = _numbers(new)
    if not old_values or not new_values:
        return False
    for previous, current in zip(old_values, new_values, strict=False):
        scale = max(abs(previous), abs(current), 1.0)
        if abs(previous - current) / scale >= 0.12:
            return True
    return False


class ClaimIntelligenceService:
    prompt_version = "claim-intelligence-v1"

    def extract_statements(self, text: str, *, limit: int = 12) -> list[ExtractedStatement]:
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = re.split(r"(?<=[.!?])\s+|(?<=;)\s+", compact)
        candidates: list[ExtractedStatement] = []
        seen: set[str] = set()
        for sentence in sentences:
            sentence = sentence.strip(" -•\t")
            normalized = sentence.lower()
            if len(sentence) < 35 or len(sentence) > 700 or normalized in seen:
                continue
            seen.add(normalized)
            tokens = _tokens(sentence)
            material_hits = len(tokens & MATERIAL_TERMS)
            has_number = bool(_numbers(sentence))
            forward_looking = any(
                marker in normalized
                for marker in ("expects", "guidance", "forecast", "will ", "target")
            )
            if not (material_hits or has_number or forward_looking):
                continue
            score = min(10, 3 + material_hits * 2 + int(has_number) + int(forward_looking))
            confidence = min(
                0.92,
                0.52 + material_hits * 0.07 + int(has_number) * 0.07,
            )
            candidates.append(
                ExtractedStatement(
                    text=sentence,
                    confidence=confidence,
                    materiality_score=score,
                    quote=sentence,
                )
            )
        candidates.sort(
            key=lambda item: (item.materiality_score, item.confidence), reverse=True
        )
        return candidates[:limit]

    def match_claims(
        self,
        db: Session,
        *,
        company_id: int,
        statement: str,
        limit: int = 3,
        minimum_similarity: float = 0.20,
    ) -> list[ClaimMatch]:
        claims = db.scalars(
            select(Claim)
            .where(Claim.company_id == company_id)
            .order_by(desc(Claim.materiality_score), desc(Claim.updated_at))
            .limit(250)
        ).all()
        matches = [
            ClaimMatch(claim=claim, similarity=_similarity(claim.statement, statement))
            for claim in claims
        ]
        matches = [
            match for match in matches if match.similarity >= minimum_similarity
        ]
        matches.sort(key=lambda match: match.similarity, reverse=True)
        return matches[:limit]

    def classify_relation(
        self,
        *,
        claim: Claim,
        candidate: str,
        similarity: float,
        evidence_date: datetime | None = None,
    ) -> RelationClassification:
        now = evidence_date or datetime.now(UTC)
        valid_until = (claim.metadata_ or {}).get("valid_until")
        if valid_until:
            try:
                deadline = datetime.fromisoformat(str(valid_until).replace("Z", "+00:00"))
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                if deadline < now:
                    return RelationClassification(
                        relation="stale",
                        confidence=0.95,
                        rationale=f"Claim validity expired at {deadline.isoformat()}.",
                    )
            except ValueError:
                pass

        lowered_claim = claim.statement.lower()
        lowered_candidate = candidate.lower()
        if similarity >= 0.30 and any(
            marker in lowered_candidate for marker in SUPERSESSION_MARKERS
        ):
            return RelationClassification(
                relation="superseded",
                confidence=min(0.96, 0.68 + similarity * 0.35),
                rationale="Newer statement contains an explicit revision or supersession marker.",
            )

        claim_negated = bool(_tokens(lowered_claim) & NEGATIONS)
        candidate_negated = bool(_tokens(lowered_candidate) & NEGATIONS)
        if similarity >= 0.32 and (
            claim_negated != candidate_negated
            or _numeric_conflict(claim.statement, candidate)
        ):
            reason = (
                "Comparable numeric values materially differ."
                if _numeric_conflict(claim.statement, candidate)
                else "Matched propositions have opposite polarity."
            )
            return RelationClassification(
                relation="contradicted",
                confidence=min(0.96, 0.70 + similarity * 0.30),
                rationale=reason,
            )

        if similarity >= 0.58:
            return RelationClassification(
                relation="supported",
                confidence=min(0.94, 0.60 + similarity * 0.35),
                rationale="The new statement closely matches the historical claim without a polarity or numeric conflict.",
            )
        return RelationClassification(
            relation="uncertain",
            confidence=max(0.45, min(0.74, 0.35 + similarity)),
            rationale="The statements are related, but deterministic evidence is insufficient for a stronger relation.",
        )

    def scan_document(
        self,
        db: Session,
        document: Document,
        *,
        auto_apply: bool = True,
    ) -> dict:
        if document.company_id is None:
            return {"document_id": document.id, "statements": 0, "suggestions": 0, "applied": 0}
        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
        source_tier = classify_source(document.source_type, document.source_url)
        suggestion_count = 0
        applied_count = 0
        affected_claim_ids: set[int] = set()
        statement_count = 0
        relation_counts: dict[str, int] = {}

        for chunk in chunks:
            for extracted in self.extract_statements(chunk.text):
                statement_count += 1
                matches = self.match_claims(
                    db,
                    company_id=document.company_id,
                    statement=extracted.text,
                    limit=1,
                )
                match = matches[0] if matches else None
                if match:
                    classification = self.classify_relation(
                        claim=match.claim,
                        candidate=extracted.text,
                        similarity=match.similarity,
                        evidence_date=document.published_at,
                    )
                    suggestion_type = {
                        "supported": "support_existing_claim",
                        "contradicted": "contradict_existing_claim",
                        "superseded": "supersede_existing_claim",
                        "stale": "review_stale_claim",
                        "uncertain": "review_related_claim",
                    }[classification.relation]
                else:
                    classification = RelationClassification(
                        relation="uncertain",
                        confidence=extracted.confidence,
                        rationale="No sufficiently similar historical claim was found.",
                    )
                    suggestion_type = "create_claim"

                duplicate = db.scalar(
                    select(EvidenceSuggestion).where(
                        EvidenceSuggestion.document_chunk_id == chunk.id,
                        EvidenceSuggestion.statement == extracted.text,
                        EvidenceSuggestion.suggested_claim_id
                        == (match.claim.id if match else None),
                    )
                )
                if duplicate:
                    continue

                suggestion = EvidenceSuggestion(
                    company_id=document.company_id,
                    document_id=document.id,
                    document_chunk_id=chunk.id,
                    suggested_claim_id=match.claim.id if match else None,
                    suggestion_type=suggestion_type,
                    statement=extracted.text,
                    relation=classification.relation,
                    rationale=classification.rationale,
                    quote=extracted.quote,
                    confidence=Decimal(str(round(classification.confidence, 4))),
                    status="pending",
                    prompt_version=self.prompt_version,
                    metadata_={
                        "materiality_score": extracted.materiality_score,
                        "similarity": round(match.similarity, 4) if match else None,
                        "source_tier": source_tier.key,
                        "automatic": True,
                    },
                )
                db.add(suggestion)
                db.flush()
                suggestion_count += 1
                relation_counts[classification.relation] = (
                    relation_counts.get(classification.relation, 0) + 1
                )

                should_apply = (
                    auto_apply
                    and match is not None
                    and classification.confidence >= 0.78
                    and source_tier.trust_score >= 0.68
                )
                if should_apply:
                    applied_claim = self.apply_suggestion(
                        db,
                        suggestion,
                        claim=match.claim,
                        automatic=True,
                    )
                    affected_claim_ids.add(applied_claim.id)
                    applied_count += 1

        db.commit()
        return {
            "document_id": document.id,
            "statements": statement_count,
            "suggestions": suggestion_count,
            "applied": applied_count,
            "relations": relation_counts,
            "source_tier": source_tier.key,
            "affected_claim_ids": sorted(affected_claim_ids),
        }

    def scan_text(
        self,
        db: Session,
        *,
        company: Company,
        text: str,
        source_type: str,
        source_url: str | None = None,
        source_reference: dict | None = None,
        auto_apply: bool = True,
    ) -> dict:
        source_tier = classify_source(source_type, source_url)
        extracted_statements = self.extract_statements(text)
        if not extracted_statements and len(text.strip()) >= 20:
            extracted_statements = [
                ExtractedStatement(
                    text=" ".join(text.split())[:700],
                    confidence=0.55,
                    materiality_score=5,
                    quote=" ".join(text.split())[:700],
                )
            ]
        suggestions: list[EvidenceSuggestion] = []
        applied = 0
        for extracted in extracted_statements:
            matches = self.match_claims(
                db,
                company_id=company.id,
                statement=extracted.text,
                limit=1,
            )
            match = matches[0] if matches else None
            classification = (
                self.classify_relation(
                    claim=match.claim,
                    candidate=extracted.text,
                    similarity=match.similarity,
                )
                if match
                else RelationClassification(
                    relation="uncertain",
                    confidence=extracted.confidence,
                    rationale="No sufficiently similar historical claim was found.",
                )
            )
            suggestion = EvidenceSuggestion(
                company_id=company.id,
                suggested_claim_id=match.claim.id if match else None,
                suggestion_type=(
                    {
                        "supported": "support_existing_claim",
                        "contradicted": "contradict_existing_claim",
                        "superseded": "supersede_existing_claim",
                        "stale": "review_stale_claim",
                        "uncertain": "review_related_claim",
                    }[classification.relation]
                    if match
                    else "create_claim"
                ),
                statement=extracted.text,
                relation=classification.relation,
                rationale=classification.rationale,
                quote=extracted.quote,
                confidence=Decimal(str(round(classification.confidence, 4))),
                status="pending",
                prompt_version=self.prompt_version,
                metadata_={
                    "materiality_score": extracted.materiality_score,
                    "similarity": round(match.similarity, 4) if match else None,
                    "source_tier": source_tier.key,
                    "source_type": source_type,
                    "source_url": source_url,
                    "source_reference": source_reference or {},
                    "automatic": True,
                },
            )
            db.add(suggestion)
            db.flush()
            suggestions.append(suggestion)
            if (
                auto_apply
                and match
                and classification.confidence >= 0.80
                and source_tier.trust_score >= 0.68
            ):
                self.apply_suggestion(
                    db, suggestion, claim=match.claim, automatic=True
                )
                applied += 1
        db.commit()
        return {
            "suggestion_ids": [suggestion.id for suggestion in suggestions],
            "suggestions": len(suggestions),
            "applied": applied,
            "relations": {
                relation: sum(
                    1 for suggestion in suggestions if suggestion.relation == relation
                )
                for relation in {
                    suggestion.relation for suggestion in suggestions
                }
            },
        }

    def apply_suggestion(
        self,
        db: Session,
        suggestion: EvidenceSuggestion,
        *,
        claim: Claim | None = None,
        automatic: bool = False,
    ) -> Claim:
        claim = claim or (
            db.get(Claim, suggestion.suggested_claim_id)
            if suggestion.suggested_claim_id
            else None
        )
        if claim is None:
            materiality = int((suggestion.metadata_ or {}).get("materiality_score", 5))
            claim = Claim(
                company_id=suggestion.company_id,
                statement=suggestion.statement,
                claim_type="source_extracted",
                status="unverified",
                confidence=suggestion.confidence,
                materiality_score=materiality,
                source_quality=(suggestion.metadata_ or {}).get(
                    "source_tier", "tier_unknown"
                ),
                created_by="automatic_extraction" if automatic else "user_approved",
                metadata_={
                    "evidence_suggestion_id": suggestion.id,
                    "prompt_version": suggestion.prompt_version,
                },
            )
            db.add(claim)
            db.flush()
            suggestion.suggested_claim_id = claim.id

        evidence_type = {
            "supported": "supports",
            "contradicted": "contradicts",
            "superseded": "supersedes",
            "stale": "context",
            "uncertain": "uncertain",
        }.get(suggestion.relation, "context")
        duplicate = db.scalar(
            select(ClaimEvidence).where(
                ClaimEvidence.claim_id == claim.id,
                ClaimEvidence.document_chunk_id == suggestion.document_chunk_id,
                ClaimEvidence.evidence_type == evidence_type,
            )
        )
        if duplicate is None:
            evidence = ClaimEvidence(
                claim_id=claim.id,
                document_id=suggestion.document_id,
                document_chunk_id=suggestion.document_chunk_id,
                source_url=(suggestion.metadata_ or {}).get("source_url"),
                evidence_type=evidence_type,
                summary=suggestion.rationale or suggestion.statement,
                quote=suggestion.quote,
                confidence=suggestion.confidence,
                source_tier=(suggestion.metadata_ or {}).get(
                    "source_tier", "tier_unknown"
                ),
                metadata_={
                    "automatic": automatic,
                    "suggestion_id": suggestion.id,
                    "relation": suggestion.relation,
                    "classifier": self.prompt_version,
                },
            )
            db.add(evidence)

        status = {
            "supported": "supported",
            "contradicted": "contradicted",
            "superseded": "superseded",
            "stale": "stale",
            "uncertain": "uncertain",
        }.get(suggestion.relation, claim.status)
        claim.status = status
        claim.last_reviewed_at = datetime.now(UTC)
        suggestion.status = "auto_applied" if automatic else "accepted"

        if status in {"contradicted", "superseded", "stale", "uncertain"}:
            change = ThesisChange(
                company_id=claim.company_id,
                from_version_id=claim.thesis_version_id,
                to_version_id=claim.thesis_version_id,
                change_type=f"claim_{status}",
                impact_direction="negative" if status in {"contradicted", "stale"} else "mixed",
                materiality_score=claim.materiality_score,
                summary=(
                    f"Automatic evidence classified claim as {status}: "
                    f"{claim.statement[:220]}"
                ),
                affected_claim_ids=[claim.id],
                affected_metrics=[],
                requires_review=True,
            )
            db.add(change)
            db.flush()
            ReviewAlertService().create_from_change(
                db,
                change,
                claim_id=claim.id,
                metadata={
                    "suggestion_id": suggestion.id,
                    "automatic": automatic,
                    "relation": status,
                },
            )
        return claim

    def scan_stale_claims(self, db: Session, company: Company | None = None) -> dict:
        statement = select(Claim)
        if company:
            statement = statement.where(Claim.company_id == company.id)
        scanned = 0
        stale = 0
        for claim in db.scalars(statement).all():
            scanned += 1
            classification = self.classify_relation(
                claim=claim,
                candidate=claim.statement,
                similarity=1.0,
            )
            if classification.relation != "stale" or claim.status == "stale":
                continue
            claim.status = "stale"
            claim.last_reviewed_at = datetime.now(UTC)
            ReviewAlertService().create_from_claim(
                db, claim, "stale", classification.rationale
            )
            stale += 1
        db.commit()
        return {"scanned": scanned, "stale": stale}
