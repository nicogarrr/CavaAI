import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "ingest_asts_official",
    Path(__file__).resolve().parent.parent / "scripts" / "ingest_asts_official.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_only_sec_filing_urls_are_accepted():
    ok = "https://www.sec.gov/Archives/edgar/data/1780312/000119312526342550/asts-20260630.htm"
    assert _mod._is_sec_filing_url(ok)
    assert not _mod._is_sec_filing_url("http://www.sec.gov/Archives/edgar/data/1/x.htm")
    assert not _mod._is_sec_filing_url("https://evil.example/Archives/edgar/data/1/x.htm")
    assert not _mod._is_sec_filing_url("https://www.sec.gov/cgi-bin/browse-edgar")
