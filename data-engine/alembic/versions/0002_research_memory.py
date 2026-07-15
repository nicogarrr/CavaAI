"""research memory tables

Revision ID: 0002_research_memory
Revises: 0001_initial
Create Date: 2026-07-09 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_research_memory"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("claim_ids", sa.JSON(), nullable=False),
        sa.Column("memory_item_ids", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_research_sessions_company_id", "research_sessions", ["company_id"], unique=False)
    op.create_index("ix_research_sessions_tenant_id", "research_sessions", ["tenant_id"], unique=False)

    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("materiality_score", sa.Integer(), nullable=False),
        sa.Column("source_quality", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(80), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claims_company_id", "claims", ["company_id"], unique=False)
    op.create_index("ix_claims_tenant_id", "claims", ["tenant_id"], unique=False)

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("research_session_id", sa.Integer(), sa.ForeignKey("research_sessions.id"), nullable=True),
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("memory_type", sa.String(80), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(80), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_items_company_id", "memory_items", ["company_id"], unique=False)
    op.create_index("ix_memory_items_research_session_id", "memory_items", ["research_session_id"], unique=False)
    op.create_index("ix_memory_items_tenant_id", "memory_items", ["tenant_id"], unique=False)

    op.create_table(
        "thesis_changes",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("from_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("to_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=True),
        sa.Column("change_type", sa.String(80), nullable=False),
        sa.Column("impact_direction", sa.String(40), nullable=False),
        sa.Column("materiality_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("affected_claim_ids", sa.JSON(), nullable=False),
        sa.Column("affected_metrics", sa.JSON(), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_thesis_changes_company_id", "thesis_changes", ["company_id"], unique=False)
    op.create_index("ix_thesis_changes_tenant_id", "thesis_changes", ["tenant_id"], unique=False)

    op.create_table(
        "thesis_sections",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("thesis_version_id", sa.Integer(), sa.ForeignKey("thesis_versions.id"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("section_key", sa.String(80), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("thesis_version_id", "section_key", name="uq_thesis_section_key"),
    )
    op.create_index("ix_thesis_sections_company_id", "thesis_sections", ["company_id"], unique=False)
    op.create_index("ix_thesis_sections_tenant_id", "thesis_sections", ["tenant_id"], unique=False)
    op.create_index("ix_thesis_sections_thesis_version_id", "thesis_sections", ["thesis_version_id"], unique=False)

    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("claim_id", sa.Integer(), sa.ForeignKey("claims.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=True),
        sa.Column("document_chunk_id", sa.Integer(), sa.ForeignKey("document_chunks.id"), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("source_tier", sa.String(40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_claim_evidence_claim_id", "claim_evidence", ["claim_id"], unique=False)
    op.create_index("ix_claim_evidence_tenant_id", "claim_evidence", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_table("claim_evidence")
    op.drop_table("thesis_sections")
    op.drop_table("thesis_changes")
    op.drop_table("memory_items")
    op.drop_table("claims")
    op.drop_table("research_sessions")
