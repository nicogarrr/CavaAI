"""Clasificacion por palabra completa: spectrum/Starlink/wireless no es dilucion."""

import pytest

from app.services.materiality_service import MaterialityService, _has_term


class _Tier:
    key = "tier_unknown"


def _types(text: str) -> list[str]:
    from app.services import materiality_service as m

    return [
        t
        for t, kws in m.MATERIAL_KEYWORDS.items()
        if any(_has_term(text.lower(), k) for k in kws)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Telecom stocks tumble on SpaceX spectrum acquisition news",
        "Shares of major U.S. telecommunications companies fell on Thursday",
        "SpaceX Buys Wireless Spectrum For Starlink; Verizon, AT&T, T-Mobile Tumble",
        "Nasdaq 100 platform steps up",
        "The second quarter was strong",
    ],
)
def test_spectrum_and_generic_share_moves_are_not_dilution(text):
    assert "dilution" not in _types(text)


@pytest.mark.parametrize(
    "text",
    [
        "Company announces $500 million convertible notes offering",
        "ASTS launches at-the-market program to sell stock",
        "Firm files ATM program for new shares",
        "Secondary offering priced at $20",
    ],
)
def test_real_dilution_still_detected(text):
    assert "dilution" in _types(text)


def test_word_boundary_helper():
    assert _has_term("fda approval", "fda")
    assert not _has_term("second", "sec")
    assert _has_term("sec filing", "sec")
    assert MaterialityService  # import guard
