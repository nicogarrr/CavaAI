"""thesis_change_types contract tests.

Claim statuses map to canonical thesis-change event names; the mapping
must be total for the known lifecycle states and reject anything else
loudly - a silently mislabelled change event corrupts thesis history.
"""

import pytest

from app.services.thesis_change_types import (
    CLAIM_CHANGE_TYPE_BY_STATUS,
    claim_change_type,
)


def test_known_statuses_map_to_canonical_events():
    assert claim_change_type("contradicted") == "claim_contradiction"
    assert claim_change_type("superseded") == "claim_superseded"
    assert claim_change_type("stale") == "claim_stale"
    assert claim_change_type("uncertain") == "claim_uncertain"
    # The mapping covers exactly the reviewable non-clean states.
    assert set(CLAIM_CHANGE_TYPE_BY_STATUS) == {
        "contradicted", "superseded", "stale", "uncertain",
    }


def test_unknown_status_raises_loudly():
    with pytest.raises(ValueError, match="Unsupported claim status"):
        claim_change_type("supported")
    with pytest.raises(ValueError, match="Unsupported claim status"):
        claim_change_type("made_up_status")
