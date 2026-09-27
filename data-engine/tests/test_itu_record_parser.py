import hashlib
from pathlib import Path

import pytest

from app.services.itu_record_parser import parse_itu_record

FIXTURES = Path(__file__).parent / "fixtures" / "itu"
URL = "https://www.itu.int/ITU-R/space/asreceived/Publication/DisplayPublication/72184"


def test_real_official_html_parses_identity_fields_with_locators():
    raw = (FIXTURES / "d2026-84958-detail.html").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "1da58c29610f9956d0ef6c3ec2eb88f7970dc71ded51d26d15fd6295256adb2a"
    record = parse_itu_record(raw, URL)
    assert record.submission_id == "72184" and record.reference == "D2026-84958"
    assert record.fields["SatName"] == "D-BLUEBIRD"
    assert record.fields["ActCode"] == "M"
    assert record.fields["NumberOfSatellites"] == "344"
    assert record.registry_date.isoformat() == "2026-09-24"
    assert record.receipt_date.isoformat() == "2026-09-24"
    assert record.frequency_url == "/ITU-R/space/asreceived/Publication/FrequenciesTable?submissionId=72184"
    assert not record.frequencies_complete
    assert all(block.metadata["field_complete"] and "locator" in block.metadata for block in record.blocks)
    assert not any("Freq From" in block.text for block in record.blocks)


def test_real_linked_fragment_parses_five_rows_but_not_page_publication_date():
    raw = (FIXTURES / "d2026-84958-detail.html").read_bytes()
    frequency = (FIXTURES / "d2026-84958-frequencies.html").read_bytes()
    assert hashlib.sha256(frequency).hexdigest() == "40245187559bdeee71a9d86c980afeb8f2fd138110b07a261411cfc0f602f807"
    record = parse_itu_record(raw, URL, frequency_html=frequency)
    bands = [block for block in record.blocks if block.metadata.get("row")]
    assert record.frequencies_complete and len(bands) == 5
    assert bands[0].text == "Freq From (MHz): 806; Freq To (MHz): 890"
    assert bands[-1].metadata["locator"] == "table#freqs tbody tr:nth-child(5)"
    # BR registry/receipt dates are not a publication date.
    assert "published_at" not in record.fields


def test_identity_mismatch_or_missing_field_fails_closed():
    raw = (FIXTURES / "d2026-84958-detail.html").read_bytes()
    with pytest.raises(ValueError, match="form missing or ambiguous"):
        parse_itu_record(raw, URL.replace("72184", "72185"))
    corrupted = raw.replace(b'data-fieldname="InternalReference"', b'data-fieldname="OtherReference"')
    with pytest.raises(ValueError, match="identity fields"):
        parse_itu_record(corrupted, URL)
    with pytest.raises(ValueError, match="frequency table"):
        parse_itu_record(raw, URL, frequency_html=b"<html>No table</html>")


def test_field_node_from_another_submission_is_rejected():
    raw = (FIXTURES / "d2026-84958-detail.html").read_bytes()
    # Change only the NumberOfSatellites node, not form or other fields.
    from lxml import html

    tree = html.fromstring(raw)
    target = tree.xpath("//*[@data-fieldname='NumberOfSatellites']")
    assert len(target) == 1 and target[0].get("data-submissionid") == "72184"
    target[0].set("data-submissionid", "99999")
    with pytest.raises(ValueError, match="another submission"):
        parse_itu_record(html.tostring(tree), URL)
