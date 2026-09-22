"""cnmv_mapping contract tests.

The CNMV issuer map is an attribution boundary: exact reviewed keys
resolve, anything unknown, partial or ambiguous stays unavailable -
identity is never guessed.
"""

from app.services.cnmv_mapping import REVIEWED_ISSUERS, resolve_issuer


def test_reviewed_entries_resolve_by_exact_keys():
    assert resolve_issuer("SAN").nif == "A-39000013"
    assert resolve_issuer("san") is not None  # case-insensitive
    assert resolve_issuer("ES0113900J37").ticker == "SAN"  # ISIN
    assert resolve_issuer("A-39000013").ticker == "SAN"  # NIF
    assert resolve_issuer("BANCO SANTANDER, S.A.").ticker == "SAN"  # legal name
    assert resolve_issuer("SANTANDER").ticker == "SAN"  # reviewed alias


def test_unknown_partial_and_empty_never_resolve():
    assert resolve_issuer("NOTREAL") is None
    assert resolve_issuer("SANTAND") is None  # partial names intentionally fail
    assert resolve_issuer("BANCO") is None  # ambiguous across several issuers
    assert resolve_issuer("") is None
    assert resolve_issuer("   ") is None


def test_seed_table_is_complete_and_consistent():
    for issuer in REVIEWED_ISSUERS:
        assert issuer.legal_name == issuer.legal_name.upper()
        assert issuer.nif.startswith("A-")
        assert issuer.isin.startswith("ES")
        assert len(issuer.isin) == 12
        # Every alias resolves back to its own issuer.
        for alias in issuer.aliases:
            assert resolve_issuer(alias) is issuer
