"""0030: upgrade/downgrade con datos preexistentes, sin perdidas.

Siembra model_aliases + decision_journal_entries (+ su company) sobre el
esquema 0029, sube a head (0030) y vuelve a bajar: las filas deben
sobrevivir intactas en ambas direcciones porque 0030 solo crea indices.
El downgrade revierte exactamente los indices que creo el upgrade.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

DATA_ENGINE_DIR = Path(__file__).resolve().parents[1]
REVISION_0029 = "0029_manager_holding_filing_date"

INDEXES_0030 = [
    ("ix_news_events_company_id", "news_events"),
    ("ix_news_events_company_date", "news_events"),
    ("ix_risk_events_company_id", "risk_events"),
    ("ix_risk_events_company_status", "risk_events"),
    ("ix_claims_thesis_version_id", "claims"),
    ("ix_claim_evidence_document_id", "claim_evidence"),
    ("ix_claim_evidence_document_chunk_id", "claim_evidence"),
    ("ix_thesis_diffs_from_version_id", "thesis_diffs"),
    ("ix_thesis_diffs_to_version_id", "thesis_diffs"),
    ("ix_thesis_changes_from_version_id", "thesis_changes"),
    ("ix_thesis_changes_to_version_id", "thesis_changes"),
    ("ix_research_reviews_thesis_change_id", "research_reviews"),
    ("ix_research_reviews_claim_id", "research_reviews"),
    ("ix_research_reviews_news_event_id", "research_reviews"),
    ("ix_evidence_suggestions_document_id", "evidence_suggestions"),
    ("ix_evidence_suggestions_suggested_claim_id", "evidence_suggestions"),
    ("ix_call_claims_linked_result_id", "call_claims"),
    ("ix_research_alerts_review_id", "research_alerts"),
    ("ix_earnings_runs_thesis_change_id", "earnings_runs"),
]


def _alembic(database_url: str, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=DATA_ENGINE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr


def _index_names(database_url: str, table: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {index["name"] for index in inspect(engine).get_indexes(table)}
    finally:
        engine.dispose()


def _seed_preexisting_rows(database_url: str) -> tuple[int, int]:
    """Siembra via ORM (0030 no anade columnas: el ORM vale sobre 0029)."""
    from sqlalchemy.orm import sessionmaker

    from app.models.entities import Company, DecisionJournalEntry, ModelAlias, Tenant

    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()
    try:
        tenant = Tenant(external_id="ext-seed-0030", name="Seed Tenant")
        db_tenant = tenant
        session.add(db_tenant)
        session.flush()
        session.add(
            ModelAlias(
                internal_alias="seed-alias-0030",
                provider="seed-provider",
                provider_model_id="seed-model-1",
                enabled=True,
                context_window=128000,
                input_cost=Decimal("0.5"),
                output_cost=Decimal("1.5"),
                supported_capabilities=["text"],
            )
        )
        company = Company(
            ticker="SEED30",
            name="Seed Preexisting Co",
            exchange="NASDAQ",
            company_type="operating",
            valuation_model="dcf",
        )
        session.add(company)
        session.flush()
        session.add(
            DecisionJournalEntry(
                tenant_id=db_tenant.id,
                company_id=company.id,
                decision_date=date(2024, 5, 1),
                decision="buy",
                rationale="seeded before 0030",
                what_must_be_true=["revenue grows"],
                price=Decimal("100.5"),
            )
        )
        session.commit()
        alias_id = session.scalar(text("SELECT id FROM model_aliases WHERE internal_alias='seed-alias-0030'")) or 0
        journal_id = session.scalar(
            text("SELECT id FROM decision_journal_entries WHERE rationale='seeded before 0030'")
        ) or 0
        return int(alias_id), int(journal_id)
    finally:
        session.close()
        engine.dispose()


def test_0030_upgrade_downgrade_preserves_preexisting_data():
    temp_dir = Path(tempfile.mkdtemp(prefix="cavaai_0030_"))
    database_url = f"sqlite:///{(temp_dir / 'preexisting.db').as_posix()}"
    try:
        _alembic(database_url, "upgrade", REVISION_0029)
        alias_id, journal_id = _seed_preexisting_rows(database_url)

        _alembic(database_url, "upgrade", "head")
        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                alias = conn.execute(
                    text("SELECT provider, context_window FROM model_aliases WHERE id=:id"),
                    {"id": alias_id},
                ).one()
                assert alias.provider == "seed-provider"
                assert alias.context_window == 128000
                journal = conn.execute(
                    text("SELECT decision, price FROM decision_journal_entries WHERE id=:id"),
                    {"id": journal_id},
                ).one()
                assert journal.decision == "buy"
                assert float(journal.price) == 100.5
        finally:
            engine.dispose()
        for name, table in INDEXES_0030:
            assert name in _index_names(database_url, table), f"{name} missing after upgrade"

        _alembic(database_url, "downgrade", REVISION_0029)
        engine = create_engine(database_url)
        try:
            with engine.connect() as conn:
                # 2 filas: la historica 'opencode-go' (0017, destructiva
                # documentada aparte) + la sembrada antes de 0030.
                assert (
                    conn.execute(text("SELECT COUNT(*) FROM model_aliases")).scalar() == 2
                )
                assert sorted(
                    row.internal_alias
                    for row in conn.execute(text("SELECT internal_alias FROM model_aliases"))
                ) == ["deepseek-v4-flash", "seed-alias-0030"]
                assert (
                    conn.execute(text("SELECT COUNT(*) FROM decision_journal_entries")).scalar()
                    == 1
                )
                assert (
                    conn.execute(
                        text("SELECT COUNT(*) FROM companies WHERE ticker='SEED30'")
                    ).scalar()
                    == 1
                )
        finally:
            engine.dispose()
        for name, table in INDEXES_0030:
            assert name not in _index_names(database_url, table), f"{name} survived downgrade"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
