"""investment knowledge, fact integrity and driver assumptions

Revision ID: 0012_knowledge_integrity
Revises: 0011_model_aliases
Create Date: 2026-07-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_knowledge_integrity"
down_revision = "0011_model_aliases"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True)


def upgrade() -> None:
    with op.batch_alter_table("fundamental_drivers") as batch:
        batch.add_column(
            sa.Column("currency", sa.String(10), nullable=False, server_default="N/A")
        )
        batch.add_column(
            sa.Column(
                "time_basis", sa.String(40), nullable=False, server_default="point_in_time"
            )
        )
        batch.add_column(
            sa.Column("geography", sa.String(120), nullable=False, server_default="global")
        )
        batch.add_column(
            sa.Column("segment", sa.String(160), nullable=False, server_default="consolidated")
        )
        batch.add_column(
            sa.Column("period", sa.String(40), nullable=False, server_default="unknown")
        )
        batch.add_column(
            sa.Column("source", sa.String(240), nullable=False, server_default="financial_fact")
        )

    op.create_table(
        "knowledge_collections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("collection_type", sa.String(80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id", "slug", name="uq_knowledge_collection_tenant_slug"
        ),
    )
    for column in ("slug", "tenant_id"):
        op.create_index(
            f"ix_knowledge_collections_{column}", "knowledge_collections", [column]
        )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_collections.id"),
            nullable=True,
        ),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(240), nullable=True),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("storage_uri", sa.String(1000), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
    )
    for column in (
        "collection_id",
        "author",
        "document_type",
        "status",
        "checksum",
        "tenant_id",
    ):
        op.create_index(
            f"ix_knowledge_documents_{column}", "knowledge_documents", [column]
        )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_document_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(500), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "knowledge_document_id",
            "chunk_index",
            name="uq_knowledge_chunk_document_index",
        ),
    )
    for column in ("knowledge_document_id", "page_number", "tenant_id"):
        op.create_index(f"ix_knowledge_chunks_{column}", "knowledge_chunks", [column])

    op.create_table(
        "investment_principles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_document_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column(
            "knowledge_chunk_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_chunks.id"),
            nullable=True,
        ),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_collections.id"),
            nullable=True,
        ),
        sa.Column("principle", sa.Text(), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("application_conditions", sa.JSON(), nullable=False),
        sa.Column("exceptions", sa.JSON(), nullable=False),
        sa.Column("applies_to_company_ids", sa.JSON(), nullable=False),
        sa.Column("exact_fragment", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("author", sa.String(240), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
    )
    for column in (
        "knowledge_document_id",
        "knowledge_chunk_id",
        "collection_id",
        "category",
        "status",
        "tenant_id",
    ):
        op.create_index(
            f"ix_investment_principles_{column}", "investment_principles", [column]
        )

    op.create_table(
        "investment_case_studies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "knowledge_document_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_documents.id"),
            nullable=True,
        ),
        sa.Column(
            "collection_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_collections.id"),
            nullable=True,
        ),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("period", sa.String(80), nullable=True),
        sa.Column("sector", sa.String(160), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("lessons", sa.JSON(), nullable=False),
        sa.Column("source_locator", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
    )
    for column in (
        "knowledge_document_id",
        "collection_id",
        "company_id",
        "sector",
        "status",
        "tenant_id",
    ):
        op.create_index(
            f"ix_investment_case_studies_{column}", "investment_case_studies", [column]
        )

    op.create_table(
        "decision_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "decision_journal_entry_id",
            sa.Integer(),
            sa.ForeignKey("decision_journal_entries.id"),
            nullable=True,
        ),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("taxonomy", sa.String(120), nullable=False),
        sa.Column("expectation", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("deviation", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("lesson", sa.Text(), nullable=False),
        sa.Column("future_application", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
    )
    for column in (
        "decision_journal_entry_id",
        "company_id",
        "taxonomy",
        "status",
        "tenant_id",
    ):
        op.create_index(f"ix_decision_lessons_{column}", "decision_lessons", [column])

    op.create_table(
        "fact_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "financial_fact_id",
            sa.Integer(),
            sa.ForeignKey("financial_facts.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            sa.Integer(),
            sa.ForeignKey("kpi_extraction_candidates.id"),
            nullable=True,
        ),
        sa.Column("previous_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("new_value", sa.Numeric(24, 8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(160), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canonical_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "financial_fact_id",
            "canonical_version",
            name="uq_fact_revision_canonical_version",
        ),
    )
    for column in ("financial_fact_id", "candidate_id", "status", "tenant_id"):
        op.create_index(f"ix_fact_revisions_{column}", "fact_revisions", [column])

    op.create_table(
        "driver_assumption_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "driver_id",
            sa.Integer(),
            sa.ForeignKey("fundamental_drivers.id"),
            nullable=False,
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(40), nullable=False),
        sa.Column("value", sa.Numeric(24, 8), nullable=False),
        sa.Column("source", sa.String(240), nullable=False),
        sa.Column("user_override", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "previous_version_id",
            sa.Integer(),
            sa.ForeignKey("driver_assumption_versions.id"),
            nullable=True,
        ),
        _tenant(),
        *_timestamps(),
    )
    for column in (
        "driver_id",
        "fiscal_year",
        "scenario",
        "user_override",
        "previous_version_id",
        "tenant_id",
    ):
        op.create_index(
            f"ix_driver_assumption_versions_{column}",
            "driver_assumption_versions",
            [column],
        )

    if op.get_bind().dialect.name == "postgresql":
        full_text_indexes = (
            ("ix_doc_chunks_fts", "document_chunks", "text"),
            ("ix_knowledge_chunks_fts", "knowledge_chunks", "content"),
            ("ix_claims_fts", "claims", "statement"),
            ("ix_thesis_sections_fts", "thesis_sections", "body"),
            ("ix_investment_principles_fts", "investment_principles", "principle"),
            ("ix_investment_cases_fts", "investment_case_studies", "summary"),
            ("ix_decision_lessons_fts", "decision_lessons", "lesson"),
        )
        for index_name, table_name, column_name in full_text_indexes:
            op.execute(
                sa.text(
                    f'CREATE INDEX "{index_name}" ON "{table_name}" '
                    f"USING GIN (to_tsvector('simple', coalesce(\"{column_name}\", '')))"
                )
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for index_name in (
            "ix_doc_chunks_fts",
            "ix_knowledge_chunks_fts",
            "ix_claims_fts",
            "ix_thesis_sections_fts",
            "ix_investment_principles_fts",
            "ix_investment_cases_fts",
            "ix_decision_lessons_fts",
        ):
            op.execute(sa.text(f'DROP INDEX IF EXISTS "{index_name}"'))
    op.drop_table("driver_assumption_versions")
    op.drop_table("fact_revisions")
    op.drop_table("decision_lessons")
    op.drop_table("investment_case_studies")
    op.drop_table("investment_principles")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_collections")
    with op.batch_alter_table("fundamental_drivers") as batch:
        for column in ("source", "period", "segment", "geography", "time_basis", "currency"):
            batch.drop_column(column)
