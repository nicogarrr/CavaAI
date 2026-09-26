"""0030 indexes and cascades

Revision ID: 0030_indexes_and_cascades
Revises: 0029_manager_holding_filing_date

Cubre los join-FK que quedaban sin indice (los filtros por
company/date y company/status hacian full scans) y deja por escrito la
politica de borrado que ya expresa el ORM en entities.py:

- CASCADE (el hijo no vive sin el padre): document_chunks,
  claim_evidence (via claim), thesis_sections/nodes/edges,
  position/cash_daily_snapshots (via portfolio_snapshot),
  insider_transactions (via filing), valuation_assumptions/outputs,
  fundamental_* (via model_version), fact_revisions, knowledge_chunks,
  saved_screen_matches, plan_contributions, workflow_step_runs.
- SET NULL (el hijo sobrevive): links nulables a thesis_versions,
  documents/document_chunks, claims, news_events, financial_facts, etc.
- RESTRICT (sin ondelete, a proposito): hechos financieros y resto de
  company_id NOT NULL — borrar una company con hechos/tesis/claims
  debe fallar en vez de amputar la pista de auditoria.

Nota SQLite/Postgres existentes: los ondelete solo se materializan en
tablas de nueva creacion (cambiar la accion de una FK exige
recrear la tabla); esta migracion solo crea indices y es totalmente
reversible. insider_transactions.filing_id ya estaba cubierto por
ix_insider_transactions_filing (0023): no se duplica.
"""

from alembic import op

revision = "0030_indexes_and_cascades"
down_revision = "0029_manager_holding_filing_date"
branch_labels = None
depends_on = None


INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_news_events_company_id", "news_events", ["company_id"]),
    ("ix_news_events_company_date", "news_events", ["company_id", "date"]),
    ("ix_risk_events_company_id", "risk_events", ["company_id"]),
    ("ix_risk_events_company_status", "risk_events", ["company_id", "status"]),
    ("ix_claims_thesis_version_id", "claims", ["thesis_version_id"]),
    ("ix_claim_evidence_document_id", "claim_evidence", ["document_id"]),
    (
        "ix_claim_evidence_document_chunk_id",
        "claim_evidence",
        ["document_chunk_id"],
    ),
    ("ix_thesis_diffs_from_version_id", "thesis_diffs", ["from_version_id"]),
    ("ix_thesis_diffs_to_version_id", "thesis_diffs", ["to_version_id"]),
    ("ix_thesis_changes_from_version_id", "thesis_changes", ["from_version_id"]),
    ("ix_thesis_changes_to_version_id", "thesis_changes", ["to_version_id"]),
    (
        "ix_research_reviews_thesis_change_id",
        "research_reviews",
        ["thesis_change_id"],
    ),
    ("ix_research_reviews_claim_id", "research_reviews", ["claim_id"]),
    (
        "ix_research_reviews_news_event_id",
        "research_reviews",
        ["news_event_id"],
    ),
    (
        "ix_evidence_suggestions_document_id",
        "evidence_suggestions",
        ["document_id"],
    ),
    (
        "ix_evidence_suggestions_suggested_claim_id",
        "evidence_suggestions",
        ["suggested_claim_id"],
    ),
    ("ix_call_claims_linked_result_id", "call_claims", ["linked_result_id"]),
    ("ix_research_alerts_review_id", "research_alerts", ["review_id"]),
    ("ix_earnings_runs_thesis_change_id", "earnings_runs", ["thesis_change_id"]),
]


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
