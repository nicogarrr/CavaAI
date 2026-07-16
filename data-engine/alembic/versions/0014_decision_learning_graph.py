"""decision learning link and universal knowledge graph

Revision ID: 0014_decision_learning_graph
Revises: 0013_screener_engine
Create Date: 2026-07-16 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_decision_learning_graph"
down_revision = "0013_screener_engine"
branch_labels = None
depends_on = None


def _tenant() -> sa.Column:
    return sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=True)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    with op.batch_alter_table("decision_lessons") as batch:
        batch.add_column(sa.Column("expectation_review_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_decision_lesson_expectation_review",
            "expectation_reviews",
            ["expectation_review_id"],
            ["id"],
        )
        batch.create_unique_constraint(
            "uq_decision_lesson_expectation_review", ["expectation_review_id"]
        )
        batch.create_index(
            "ix_decision_lessons_expectation_review_id", ["expectation_review_id"]
        )

    op.create_table(
        "knowledge_graph_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("node_key", sa.String(240), nullable=False),
        sa.Column("node_type", sa.String(80), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "node_key", name="uq_knowledge_graph_node_key"),
    )
    for column in (
        "node_key", "node_type", "company_id", "entity_type", "entity_id", "status", "tenant_id"
    ):
        op.create_index(
            f"ix_knowledge_graph_nodes_{column}", "knowledge_graph_nodes", [column]
        )

    op.create_table(
        "knowledge_graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "from_node_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_graph_nodes.id"),
            nullable=False,
        ),
        sa.Column(
            "to_node_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_graph_nodes.id"),
            nullable=False,
        ),
        sa.Column("edge_type", sa.String(120), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.String(160), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        _tenant(),
        *_timestamps(),
        sa.UniqueConstraint(
            "tenant_id",
            "from_node_id",
            "to_node_id",
            "edge_type",
            name="uq_knowledge_graph_edge",
        ),
    )
    for column in ("from_node_id", "to_node_id", "edge_type", "status", "tenant_id"):
        op.create_index(
            f"ix_knowledge_graph_edges_{column}", "knowledge_graph_edges", [column]
        )


def downgrade() -> None:
    op.drop_table("knowledge_graph_edges")
    op.drop_table("knowledge_graph_nodes")
    with op.batch_alter_table("decision_lessons") as batch:
        batch.drop_index("ix_decision_lessons_expectation_review_id")
        batch.drop_constraint("uq_decision_lesson_expectation_review", type_="unique")
        batch.drop_constraint("fk_decision_lesson_expectation_review", type_="foreignkey")
        batch.drop_column("expectation_review_id")
