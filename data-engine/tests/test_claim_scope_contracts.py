"""Contract tests for claim scoping and the approval state machine.

Claims are written per ThesisVersion, but five consumers read them by
``company_id`` alone. The red team penalises every material claim that has no
evidence (-8 points each), so three regenerations of a healthy thesis drove
``red_team_score`` to 0/100: the score measured how many times the thesis had
been regenerated, not the risk.

The approval gate is the only human barrier before a thesis is treated as
current, and it had two write paths with different vocabularies and no
validation, so a version generated as ``insufficient_data`` could be marked
approved while its own memo read "NO VALUATION - insufficient data".
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Claim, Company, ThesisVersion
from app.models.entities import Base
from app.services.claim_scope import (
    claims_for_thesis,
    latest_thesis_version,
    live_claims,
    supersede_claims_of,
)
from app.services.thesis_approval_service import _assert_approvable


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _company(db, ticker="SCOPE"):
    row = Company(
        ticker=ticker,
        name=ticker,
        exchange="TEST",
        currency="USD",
        sector="Technology",
        industry="Software",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    db.add(row)
    db.flush()
    return row


def _thesis(db, company, version, *, status="draft", markdown=None):
    row = ThesisVersion(
        company_id=company.id,
        version=version,
        status=status,
        thesis_markdown=markdown or f"# v{version}",
        executive_summary=f"summary v{version}",
    )
    db.add(row)
    db.flush()
    return row


def _claim(db, company, thesis, *, materiality=8, status="supported", statement=None):
    row = Claim(
        company_id=company.id,
        thesis_version_id=thesis.id if thesis else None,
        statement=statement or f"claim {materiality}",
        claim_type="generated_thesis",
        status=status,
        confidence=Decimal("0.9"),
        materiality_score=materiality,
        source_quality="tier_1_regulatory",
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------------
# scoping
# --------------------------------------------------------------------------


def test_superseded_version_claims_are_excluded_from_live_claims(db):
    company = _company(db)
    v1 = _thesis(db, company, 1)
    v2 = _thesis(db, company, 2)
    _claim(db, company, v1, materiality=8)
    _claim(db, company, v2, materiality=8)
    db.commit()

    supersede_claims_of(db, company.id, v1.id)
    db.commit()

    live = live_claims(db, company)
    assert [c.thesis_version_id for c in live] == [v2.id]
    assert len(live) == 1


def test_live_claims_includes_company_level_claims(db):
    """Claims not yet attached to a thesis are legitimate inputs."""
    company = _company(db)
    v1 = _thesis(db, company, 1)
    _claim(db, company, None, materiality=7)
    _claim(db, company, v1, materiality=9)
    db.commit()

    live = live_claims(db, company)
    assert len(live) == 2


def test_live_claims_excludes_other_versions_even_without_supersede(db):
    """Even if the supersede step is missed, the read is scoped."""
    company = _company(db)
    _thesis(db, company, 1)
    v3 = _thesis(db, company, 3)
    _claim(db, company, db.query(ThesisVersion).filter_by(version=1).one(), materiality=8)
    _claim(db, company, v3, materiality=8)
    db.commit()

    assert latest_thesis_version(db, company).id == v3.id
    assert [c.thesis_version_id for c in live_claims(db, company)] == [v3.id]


def test_live_claims_count_is_stable_across_regenerations(db):
    """The read must not grow with the number of regenerations.

    This is the regression that mattered: red_team_score fell by ~40 points
    per regeneration because each one added another orphan claim with
    materiality >= 7 and no evidence.
    """
    company = _company(db)
    scores = []
    for version in (1, 2, 3, 4):
        previous = latest_thesis_version(db, company)
        thesis = _thesis(db, company, version)
        if previous is not None:
            supersede_claims_of(db, company.id, previous.id)
        # One material claim with no evidence, as the generator produces.
        _claim(db, company, thesis, materiality=8, status="unverified")
        db.commit()
        live = live_claims(db, company)
        scores.append(sum(1 for c in live if c.materiality_score >= 7 and not list(c.evidence)))
    assert scores == [1, 1, 1, 1]


def test_claims_for_thesis_is_strict(db):
    company = _company(db)
    v1 = _thesis(db, company, 1)
    v2 = _thesis(db, company, 2)
    _claim(db, company, v1, materiality=8)
    _claim(db, company, v2, materiality=8)
    _claim(db, company, None, materiality=8)
    db.commit()

    assert len(claims_for_thesis(db, company, v2.id)) == 1
    # None means "not yet attached to a thesis", NOT "everything".
    assert len(claims_for_thesis(db, company, None)) == 1


def test_supersede_is_idempotent(db):
    company = _company(db)
    v1 = _thesis(db, company, 1)
    _claim(db, company, v1, status="supported")
    db.commit()

    assert supersede_claims_of(db, company.id, v1.id) == 1
    assert supersede_claims_of(db, company.id, v1.id) == 0


# --------------------------------------------------------------------------
# approval state machine
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["insufficient_data", "draft_failed_audit"])
def test_a_version_that_says_it_is_not_publishable_cannot_be_approved(db, status):
    company = _company(db, ticker=f"APP{status[:3]}")
    thesis = _thesis(db, company, 1, status=status, markdown="# NO VALUATION")
    db.commit()

    with pytest.raises(ValueError) as exc:
        _assert_approvable(db, thesis)
    assert status in str(exc.value)


def test_a_draft_can_be_approved(db):
    company = _company(db, ticker="APPROK")
    thesis = _thesis(db, company, 1, status="draft")
    db.commit()

    _assert_approvable(db, thesis)  # no raise


def test_approving_a_stale_version_is_refused(db):
    company = _company(db, ticker="APPSTALE")
    v1 = _thesis(db, company, 1, status="draft")
    _thesis(db, company, 2, status="draft")
    db.commit()

    with pytest.raises(ValueError) as exc:
        _assert_approvable(db, v1)
    assert "stale" in str(exc.value)
