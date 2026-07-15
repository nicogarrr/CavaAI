CLAIM_CHANGE_TYPE_BY_STATUS = {
    "contradicted": "claim_contradiction",
    "superseded": "claim_superseded",
    "stale": "claim_stale",
    "uncertain": "claim_uncertain",
}


def claim_change_type(status: str) -> str:
    """Return the canonical thesis-change event name for a claim status."""
    try:
        return CLAIM_CHANGE_TYPE_BY_STATUS[status]
    except KeyError as exc:
        raise ValueError(f"Unsupported claim status for thesis change: {status}") from exc
