"""ESEF snapshot builder — reviewed-issuer join, latest-per-LEI, honest skips."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from build_esef_snapshots import build, latest_filing_per_lei  # noqa: E402
from app.services.connectors.esef import EsefFiling, EsefError  # noqa: E402


def _filing(lei: str, period_end: str, with_json: bool = True) -> EsefFiling:
    return EsefFiling(
        fxo_id=f"{lei}-{period_end}-ESEF-ES-0",
        lei=lei,
        country="ES",
        period_end=period_end,
        json_url=f"/{lei}/x.json" if with_json else None,
        package_url=f"/{lei}/x.zip",
        sha256="abc",
        error_count=0,
        warning_count=0,
    )


class FakeClient:
    """EsefClient stand-in: no network, canned names/docs."""

    def __init__(self, filings, names, docs):
        self._filings = filings
        self._names = names
        self._docs = docs

    async def list_all_filings(self, country):
        return self._filings

    async def get_entity_name(self, lei):
        name = self._names.get(lei)
        if name is None:
            raise EsefError("unknown LEI")
        return name

    async def fetch_filing_json(self, filing):
        return self._docs[filing.lei]


LEI_ITX = "95980020140005949050"
LEI_UNKNOWN = "95980020140005000000"

DOC = {
    "facts": {
        "fact-1": {
            "value": "1000",
            "decimals": 0,
            "dimensions": {
                "concept": "ifrs-full:Revenue",
                "entity": f"scheme:{LEI_ITX}",
                "period": "2024-02-01T00:00:00/2025-01-31T00:00:00",
                "unit": "iso4217:EUR",
            },
        }
    }
}


def test_latest_filing_per_lei_picks_newest_with_json():
    old = _filing(LEI_ITX, "2022-01-31")
    new = _filing(LEI_ITX, "2025-01-31")
    zip_only = _filing(LEI_ITX, "2025-06-30", with_json=False)  # newer but no json
    best = latest_filing_per_lei([new, old, zip_only])
    assert best[LEI_ITX].period_end == "2025-01-31"


def test_latest_filing_per_lei_skips_lei_without_any_json():
    assert latest_filing_per_lei([_filing(LEI_UNKNOWN, "2025-01-31", with_json=False)]) == {}


def test_build_writes_snapshot_only_for_reviewed_issuers(tmp_path):
    asyncio.run(_test_build_writes_snapshot_only_for_reviewed_issuers_impl(tmp_path))


async def _test_build_writes_snapshot_only_for_reviewed_issuers_impl(tmp_path):
    filings = [_filing(LEI_ITX, "2025-01-31"), _filing(LEI_UNKNOWN, "2025-03-31")]
    names = {
        LEI_ITX: "INDUSTRIA DE DISEÑO TEXTIL, S.A.",
        LEI_UNKNOWN: "EMPRESA NO REVISADA, S.A.",
    }
    client = FakeClient(filings, names, {LEI_ITX: DOC})
    manifest = await build(tmp_path, "ES", "2026-09-24", client)

    assert LEI_ITX in manifest["issuers"]
    assert manifest["issuers"][LEI_ITX]["ticker"] == "ITX"
    assert manifest["unresolved"] == {LEI_UNKNOWN: "EMPRESA NO REVISADA, S.A."}

    snap = json.loads((tmp_path / "snapshots" / f"{LEI_ITX}.json").read_text())
    assert snap["ticker"] == "ITX"
    assert snap["period_end"] == "2025-01-31"
    assert snap["fetched_at"] == "2026-09-24"
    rev = snap["facts"]["ifrs-full:Revenue"]["iso4217:EUR"][0]
    assert rev["val"] == "1000"  # string preserved
    assert rev["start"] == "2024-02-01"
    assert (tmp_path / "manifest.json").exists()


def test_build_marks_failed_entity_lookup_unresolved_not_guessed(tmp_path):
    asyncio.run(_test_build_marks_failed_entity_lookup_unresolved_not_guessed_impl(tmp_path))


async def _test_build_marks_failed_entity_lookup_unresolved_not_guessed_impl(tmp_path):
    filings = [_filing(LEI_UNKNOWN, "2025-03-31")]
    client = FakeClient(filings, names={}, docs={})  # lookup fails
    manifest = await build(tmp_path, "ES", "2026-09-24", client)
    assert manifest["issuers"] == {}
    assert manifest["unresolved"][LEI_UNKNOWN] == "<entity lookup failed>"
    assert not list((tmp_path / "snapshots").iterdir()) if (tmp_path / "snapshots").exists() else True
