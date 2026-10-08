"""RAG de conocimiento profesional: registro de fuentes y bloques padre."""
import sqlalchemy as sa

from alembic import op

revision = "0052_knowledge_rag"
down_revision = "0051_paper_trading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_rag_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("author", sa.String(300), nullable=True),
        sa.Column("source_uri", sa.String(1000), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("corpus", sa.String(16), nullable=False),
        sa.Column("rights", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("extractor", sa.String(64), nullable=True),
        sa.Column("parent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "sha256", name="uq_knowledge_rag_sources_tenant_sha"),
    )
    op.create_index("ix_knowledge_rag_sources_tenant_id", "knowledge_rag_sources", ["tenant_id"])
    op.create_index("ix_knowledge_rag_sources_status", "knowledge_rag_sources", ["status"])
    op.create_table(
        "knowledge_rag_parents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_rag_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("section_path", sa.JSON(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
    )
    op.create_index("ix_knowledge_rag_parents_tenant_id", "knowledge_rag_parents", ["tenant_id"])
    op.create_index("ix_knowledge_rag_parents_source", "knowledge_rag_parents", ["source_id", "ordinal"])


def downgrade() -> None:
    op.drop_table("knowledge_rag_parents")
    op.drop_table("knowledge_rag_sources")
