"""Ejes y unidades reales de Visa y Berkshire (FIX5-5, FIX5-9)."""

import io

from app.services.class_filer_eps_service import pick_member
from app.services.connectors.sec_xbrl_instance import parse_instance_dimensioned_facts

_NS = (
    'xmlns="http://www.xbrl.org/2003/instance" '
    'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
    'xmlns:us-gaap="http://fasb.org/us-gaap/2024" '
    'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
    'xmlns:xbrli="http://www.xbrl.org/2003/instance"'
)


def _instance(axis: str, member: str, eps_unit: str, share_unit: str) -> bytes:
    return f"""<xbrl {_NS}>
<unit id="{eps_unit}"><divide><unitNumerator><measure>iso4217:USD</measure></unitNumerator>
<unitDenominator><measure>xbrli:shares</measure></unitDenominator></divide></unit>
<unit id="{share_unit}"><measure>xbrli:shares</measure></unit>
<context id="c1"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier>
<segment><xbrldi:explicitMember dimension="{axis}">{member}</xbrldi:explicitMember></segment></entity>
<period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period></context>
<us-gaap:EarningsPerShareDiluted contextRef="c1" unitRef="{eps_unit}">8.5</us-gaap:EarningsPerShareDiluted>
<us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding contextRef="c1" unitRef="{share_unit}">2000000</us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding>
</xbrl>""".encode()


def test_brk_unit_ids_resolve_through_their_measures():
    facts = parse_instance_dimensioned_facts(
        io.BytesIO(
            _instance(
                "us-gaap:StatementClassOfStockAxis",
                "brka:CommonClassAMember",
                "U_UnitedStatesOfAmericaDollarsShare",
                "U_shares",
            )
        )
    )
    assert {f.tag for f in facts} == {
        "EarningsPerShareDiluted",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    }


def test_eps_unit_with_share_only_measure_is_still_rejected():
    raw = _instance("us-gaap:StatementClassOfStockAxis", "v:CommonClassAMember", "U_a", "U_b").replace(
        b'unitRef="U_a"', b'unitRef="U_b"'
    )
    facts = parse_instance_dimensioned_facts(io.BytesIO(raw))
    assert "EarningsPerShareDiluted" not in {f.tag for f in facts}


def test_visa_statement_class_of_stock_axis_is_a_class_axis():
    facts = parse_instance_dimensioned_facts(
        io.BytesIO(
            _instance(
                "us-gaap:StatementClassOfStockAxis",
                "v:CommonClassAMember",
                "U_usdPerShare",
                "U_shares",
            )
        )
    )
    assert pick_member(facts, None) == "CommonClassAMember"


def test_segment_axis_is_still_not_a_class_axis():
    facts = parse_instance_dimensioned_facts(
        io.BytesIO(
            _instance(
                "us-gaap:StatementBusinessSegmentsAxis",
                "v:CommonClassAMember",
                "U_usdPerShare",
                "U_shares",
            )
        )
    )
    assert pick_member(facts, None) is None


def test_norm_symbol_treats_share_class_separators_as_the_same_issuer():
    from app.services.financial_ingestion_service import _norm_symbol

    assert _norm_symbol("BRK-B") == _norm_symbol("BRK.B") == _norm_symbol("brk/b")
    assert _norm_symbol("BRK-B") != _norm_symbol("BRK-A")
    assert _norm_symbol("AAPL") != _norm_symbol("MSFT")


def _bad_unit_instance(num: str, den: str | None, metric: str = "EarningsPerShareDiluted") -> bytes:
    unit = (
        f"<unit id=\"U_x\"><divide><unitNumerator><measure>{num}</measure></unitNumerator>"
        f"<unitDenominator><measure>{den}</measure></unitDenominator></divide></unit>"
        if den
        else f"<unit id=\"U_x\"><measure>{num}</measure></unit>"
    )
    return f"""<xbrl {_NS}>{unit}
<context id="c1"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier>
<segment><xbrldi:explicitMember dimension="us-gaap:StatementClassOfStockAxis">v:CommonClassAMember</xbrldi:explicitMember></segment></entity>
<period><startDate>2024-01-01</startDate><endDate>2024-12-31</endDate></period></context>
<us-gaap:{metric} contextRef="c1" unitRef="U_x">8.5</us-gaap:{metric}></xbrl>""".encode()


def _tags(raw: bytes) -> set[str]:
    return {f.tag for f in parse_instance_dimensioned_facts(io.BytesIO(raw))}


def test_eps_requires_currency_per_share_structure():
    assert _tags(_bad_unit_instance("iso4217:USD", "xbrli:shares")) == {"EarningsPerShareDiluted"}
    assert _tags(_bad_unit_instance("xbrli:shares", "iso4217:USD")) == set()
    assert _tags(_bad_unit_instance("xbrli:shares", "xbrli:shares")) == set()
    assert _tags(_bad_unit_instance("iso4217:USD", None)) == set()


def test_share_count_requires_a_simple_shares_unit():
    m = "WeightedAverageNumberOfDilutedSharesOutstanding"
    assert _tags(_bad_unit_instance("xbrli:shares", None, m)) == {m}
    assert _tags(_bad_unit_instance("iso4217:USD", "xbrli:shares", m)) == set()
    assert _tags(_bad_unit_instance("xbrli:shares", "xbrli:shares", m)) == set()


def test_undeclared_unit_fails_closed():
    raw = _bad_unit_instance("iso4217:USD", "xbrli:shares").replace(b'unitRef="U_x"', b'unitRef="U_missing"')
    assert _tags(raw) == set()
