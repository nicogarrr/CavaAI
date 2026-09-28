"""Mirror SEC->HF: el sync resuelve CIK, descarga companyfacts + submissions
+ historicos y sube al dataset SOLO lo que cambio (sha1). Sin credenciales
falla cerrado (exit 2) antes de tocar la red."""

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import sec_hf_mirror_sync as sync  # noqa: E402


class _Resp:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSECClient:
    """httpx.Client falso: sirve company_tickers, companyfacts y submissions
    (con un fichero historico) desde memoria."""

    def __init__(self, *a, **k):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        self.calls.append(url)
        if url.endswith("company_tickers.json"):
            return _Resp({"0": {"cik_str": 123, "ticker": "XYZ", "title": "XYZ Corp"}})
        if "companyfacts" in url:
            return _Resp({"cik": 123, "facts": {"us-gaap": {}}})
        if url.endswith("CIK0000000123-submissions-001.json"):
            return _Resp({"accessionNumber": ["A9"], "form": ["10-K"], "reportDate": ["2019-12-31"]})
        if "submissions" in url:
            return _Resp({"filings": {
                "recent": {"accessionNumber": ["A1"], "form": ["10-K"], "reportDate": ["2025-12-31"]},
                "files": [{"name": "CIK0000000123-submissions-001.json"}],
            }})
        raise AssertionError(f"URL inesperada: {url}")


class _FakeHfApi:
    def __init__(self, token=None):
        self.uploads = {}
        self.existing_oids = {}

    def create_repo(self, *a, **k):
        self.created = True

    def get_paths_info(self, dataset, paths, repo_type=None):
        class Meta:
            def __init__(self, oid):
                self.lfs = {"oid": oid} if oid else None
        return [Meta(self.existing_oids.get(p)) for p in paths]

    def upload_file(self, *, path_or_fileobj, path_in_repo, **k):
        self.uploads[path_in_repo] = path_or_fileobj


@pytest.fixture
def fake_hf(monkeypatch):
    api = _FakeHfApi()
    module = types.ModuleType("huggingface_hub")
    module.HfApi = lambda token=None: api
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    monkeypatch.setattr(sync.httpx, "Client", _FakeSECClient)
    monkeypatch.setattr(sync.time, "sleep", lambda *_a: None)
    return api


def _tickers_file(tmp_path, monkeypatch, text="XYZ\n# comentario\n\n"):
    f = tmp_path / "sec_mirror_tickers.txt"
    f.write_text(text)
    monkeypatch.setattr(sync, "TICKERS_FILE", f)
    return f


def test_sync_sube_layout_oficial_y_manifest(tmp_path, monkeypatch, fake_hf):
    _tickers_file(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_TOKEN", "t")
    monkeypatch.setenv("HF_DATASET", "nico/cavaai-sec-mirror")
    assert sync.main() == 0
    esperado = {
        "company_tickers.json",
        "companyfacts/CIK0000000123.json",
        "submissions/CIK0000000123.json",
        "submissions/CIK0000000123-submissions-001.json",
        "manifest.json",
    }
    assert set(fake_hf.uploads) == esperado
    manifest = json.loads(fake_hf.uploads["manifest.json"])
    assert manifest == {"tickers": {"XYZ": "0000000123"}}


def test_sync_no_resube_lo_que_no_cambio(tmp_path, monkeypatch, fake_hf):
    _tickers_file(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_TOKEN", "t")
    monkeypatch.setenv("HF_DATASET", "d")
    assert sync.main() == 0
    # Segunda corrida: marca todos los sha1 como ya existentes.
    import hashlib
    fake_hf.existing_oids = {
        path: hashlib.sha1(content).hexdigest()
        for path, content in fake_hf.uploads.items()
    }
    fake_hf.uploads = {}
    assert sync.main() == 0
    assert fake_hf.uploads == {}


def test_sync_sin_credenciales_falla_cerrado(tmp_path, monkeypatch):
    _tickers_file(tmp_path, monkeypatch)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_DATASET", raising=False)
    assert sync.main() == 2
