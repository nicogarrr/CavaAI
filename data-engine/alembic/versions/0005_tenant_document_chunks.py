"""tenant-scope document chunks

Revision ID: 0005_tenant_document_chunks
Revises: 0004_research_automation
Create Date: 2026-07-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_tenant_document_chunks"
down_revision = "0004_research_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("document_chunks")}
    if "tenant_id" not in columns:
        with op.batch_alter_table("document_chunks") as batch:
            batch.add_column(sa.Column("tenant_id", sa.Integer(), nullable=True))

    # Existing chunks inherit ownership from their canonical parent document.
    op.execute(
        sa.text(
            "UPDATE document_chunks SET tenant_id = "
            "(SELECT documents.tenant_id FROM documents "
            "WHERE documents.id = document_chunks.document_id) "
            "WHERE tenant_id IS NULL"
        )
    )

    inspector = sa.inspect(bind)
    index_names = {
        index["name"]
        for index in inspector.get_indexes("document_chunks")
        if index.get("name")
    }
    if "ix_document_chunks_tenant_id" not in index_names:
        op.create_index(
            "ix_document_chunks_tenant_id",
            "document_chunks",
            ["tenant_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    index_names = {
        index["name"]
        for index in inspector.get_indexes("document_chunks")
        if index.get("name")
    }
    if "ix_document_chunks_tenant_id" in index_names:
        op.drop_index("ix_document_chunks_tenant_id", table_name="document_chunks")
    columns = {column["name"] for column in inspector.get_columns("document_chunks")}
    if "tenant_id" in columns:
        with op.batch_alter_table("document_chunks") as batch:
            batch.drop_column("tenant_id")
