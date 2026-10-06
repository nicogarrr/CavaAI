from app.services.investor_profiles import PUBLIC_PROFILES, public_profile, validate_profile
from app.services.investors import INVESTORS, investor_detail


def test_every_public_profile_is_traceable():
    assert PUBLIC_PROFILES
    for slug, profile in PUBLIC_PROFILES.items():
        assert validate_profile(profile) == [], slug


def test_profiles_only_for_investors_without_13f():
    ciks = {inv.slug: inv.cik for inv in INVESTORS}
    for slug in PUBLIC_PROFILES:
        assert slug in ciks and ciks[slug] is None


def test_validator_rejects_fact_without_source_or_date():
    bad = {"facts": [{"label": "X", "value": "1", "as_of": "", "source_url": "http://x", "kind": "otro"}], "vehicle": {}}
    problems = validate_profile(bad)
    assert any("falta as_of" in p for p in problems)
    assert any("no https" in p for p in problems)
    assert any("kind invalido" in p for p in problems)


def test_detail_of_non_13f_investor_carries_public_profile_or_none():
    from tests.test_investors import _db

    db = _db()
    detail = investor_detail(db, "quintana")
    assert detail["has_13f"] is False
    assert detail["public_profile"]["vehicle"]["regulator_id"] == "ISIN ES0173311103"
    assert detail["public_profile"]["holdings"] is None
    assert investor_detail(db, "lynch")["public_profile"] is None
    assert public_profile("buffett") is None


def test_urls_are_ascii_only():
    for slug, profile in PUBLIC_PROFILES.items():
        urls = [profile["vehicle"]["source_url"]]
        urls += [f["source_url"] for f in profile["facts"]]
        urls += [x["url"] for x in (*profile["letters"], *profile["meetings"], *profile["links"])]
        assert all(u.isascii() and " " not in u for u in urls), slug


def test_no_hardcoded_nav_that_goes_stale():
    for profile in PUBLIC_PROFILES.values():
        assert not any("liquidativo" in f["label"].lower() for f in profile["facts"])


def test_list_flags_public_profile_only_where_it_exists():
    from app.services.investors import list_investors
    from tests.test_investors import _db

    by_slug = {i["slug"]: i for i in list_investors(_db())["investors"]}
    assert by_slug["quintana"]["has_public_profile"] is True
    assert by_slug["lynch"]["has_public_profile"] is False
    assert by_slug["buffett"]["has_public_profile"] is False


def test_five_non_13f_managers_have_traceable_profiles_and_lynch_stays_empty():
    for slug in ("mark-leonard", "bezos", "munger", "nick-sleep"):
        profile = public_profile(slug)
        assert profile is not None, slug
        assert validate_profile(profile) == [], slug
        assert profile["holdings"] is None and profile["holdings_note"].startswith("Sin datos")
        assert profile["facts"] and profile["letters"]
    # Lynch: no hay fuente primaria incorporada, no se inventa ficha
    assert public_profile("lynch") is None


def test_no_profile_invents_a_portfolio():
    for slug, profile in PUBLIC_PROFILES.items():
        assert profile["holdings"] is None, slug
