"""F301: las cadenas visibles de revisiones/alertas se generan en español."""

from app.services.review_copy import (
    CHANGE_TYPE_LABELS,
    change_type_label,
    claim_status_label,
)
from app.services.thesis_change_types import CLAIM_CHANGE_TYPE_BY_STATUS


def test_change_type_label_covers_full_catalog():
    # Catálogo completo: los literales de change_type y los derivados de claim.
    literals = {
        "earnings_update",
        "news_material_positive",
        "news_material_update",
        "news_potential_invalidation",
    }
    derived = set(CLAIM_CHANGE_TYPE_BY_STATUS.values())
    assert literals | derived <= set(CHANGE_TYPE_LABELS)
    for code in literals | derived:
        label = change_type_label(code)
        assert label != code
        assert "_" not in label


def test_change_type_label_unknown_is_honest_fallback():
    label = change_type_label("algo_que_no_existe")
    assert label == "cambio en la tesis"
    assert "_" not in label


def test_claim_status_label_covers_full_catalog():
    for status in {"contradicted", "superseded", "stale", "uncertain", "supported"}:
        label = claim_status_label(status)
        assert label != status
    assert claim_status_label("otro") == "con estado desconocido"
