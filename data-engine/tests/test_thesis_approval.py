"""Tests herméticos de la aprobación de tesis por Telegram.

Sin red: el POST a Telegram (sendMessage / answerCallbackQuery) y el GET
getUpdates se sustituyen por dobles en memoria (mismo patrón que
test_telegram_notifications.py). La persistencia usa el SQLite de tests.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.database import SessionLocal, init_db
from app.models import Company, ThesisSection, ThesisVersion
from app.services import thesis_approval_service as approval


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


class _FakeGetResponse(_FakeResponse):
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _FakePostClient:
    """Doble de httpx.Client solo para POST (sendMessage)."""

    calls: list = []

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, json: dict):
        self.calls.append((url, json))
        return _FakeResponse()


class _FakePollClient:
    """Doble de httpx.Client para GET getUpdates + POST answerCallbackQuery."""

    calls: list = []
    updates_payload: dict = {"ok": True, "result": []}

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, url: str, params: dict | None = None):
        self.calls.append(("get", url, params))
        return _FakeGetResponse(self.updates_payload)

    def post(self, url: str, json: dict):
        self.calls.append(("post", url, json))
        return _FakeResponse()


class _FailingClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url: str, json: dict):
        raise ConnectionError("red caída (simulada)")


def _enabled_settings(**overrides):
    base = {
        "telegram_enabled": True,
        "telegram_approval_enabled": True,
        "telegram_bot_token": "test-token",
        "telegram_chat_id": "12345",
        "telegram_api_base_url": "https://api.telegram.org",
        "telegram_timeout_seconds": 10,
        "telegram_approval_state_path": "./storage/test-approval-offset",
        "telegram_approval_poll_interval_seconds": 15,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def db_thesis():
    init_db()
    db = SessionLocal()
    ticker = f"A{uuid4().hex[:8].upper()}"
    company = Company(
        ticker=ticker,
        name="Approval Test",
        exchange="TEST",
        currency="USD",
        sector="Technology",
        industry="Software",
        company_type="operating_company",
        valuation_model="standard_dcf",
        factor_tags=["software"],
    )
    db.add(company)
    db.flush()
    thesis = ThesisVersion(
        company_id=company.id,
        version=1,
        status="final",
        thesis_markdown="# Tesis",
        executive_summary="Resumen ejecutivo de prueba.",
        rating="watch",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    thesis_id, company_id = thesis.id, company.id
    try:
        yield db, thesis_id, ticker
    finally:
        for section in (
            db.query(ThesisSection)
            .filter(ThesisSection.thesis_version_id == thesis_id)
            .all()
        ):
            db.delete(section)
        db.delete(db.get(ThesisVersion, thesis_id))
        db.delete(db.get(Company, company_id))
        db.commit()
        db.close()


def test_approval_disabled_by_default():
    assert Settings(_env_file=None).telegram_approval_enabled is False


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("thesis:approve:7", {"decision": "approve", "thesis_id": 7}),
        ("thesis:reject:123", {"decision": "reject", "thesis_id": 123}),
    ],
)
def test_parse_valid_callbacks(data, expected):
    assert approval.parse_approval_callback(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        None,
        123,
        "",
        "thesis:approve",
        "thesis:approve:7:extra",
        "alert:approve:7",
        "thesis:publish:7",
        "thesis:approve:abc",
        "thesis:approve:-3",
        "thesis:approve:0",
        "thesis:approve:7; DROP TABLE thesis_versions",
        "thesis:approve: 7",
        " thesis :approve:7",
    ],
)
def test_parse_invalid_callbacks_rejected(data):
    assert approval.parse_approval_callback(data) is None


def test_keyboard_roundtrips_through_parser():
    keyboard = approval.build_approval_keyboard(42)
    rows = keyboard["inline_keyboard"]
    assert len(rows) == 1 and len(rows[0]) == 2
    texts = [b["text"] for b in rows[0]]
    assert any("Publicar" in t for t in texts)
    assert any("Revisar" in t for t in texts)
    parsed = [approval.parse_approval_callback(b["callback_data"]) for b in rows[0]]
    assert parsed == [
        {"decision": "approve", "thesis_id": 42},
        {"decision": "reject", "thesis_id": 42},
    ]


def test_payload_has_no_parse_mode_and_no_token():
    payload = approval.build_approval_payload(9, "hola", "12345")
    assert "parse_mode" not in payload
    assert "test-token" not in str(payload)
    assert payload["chat_id"] == "12345"
    assert "reply_markup" in payload


def test_approval_text_is_plain_and_truncated():
    text = approval.build_approval_text("san", 2, "final", "x" * 5000)
    assert "SAN" in text and "v2" in text
    assert len(text) <= 4096


def test_iter_callback_decisions_ignores_noise():
    payload = {
        "ok": True,
        "result": [
            {"update_id": 1, "message": {"text": "hola"}},
            {"update_id": 2, "callback_query": {"id": "q1", "data": "basura"}},
            {
                "update_id": 3,
                "callback_query": {"id": "q2", "data": "thesis:approve:5"},
            },
            {
                "update_id": 4,
                "callback_query": {"id": "q3", "data": "thesis:reject:9"},
            },
            {"update_id": 5, "callback_query": {"id": "q4", "data": "thesis:approve:999999"}},
        ],
    }
    out = approval.iter_callback_decisions(payload)
    assert [(d["update_id"], d["decision"], d["thesis_id"]) for d in out] == [
        (3, "approve", 5),
        (4, "reject", 9),
        (5, "approve", 999999),
    ]
    assert approval.iter_callback_decisions({}) == []
    assert approval.iter_callback_decisions(None) == []


def test_send_skipped_when_disabled_does_no_network(monkeypatch, db_thesis):
    _FakePostClient.calls.clear()
    monkeypatch.setattr(approval.httpx, "Client", _FakePostClient)
    monkeypatch.setattr(
        approval, "get_settings", lambda: _enabled_settings(telegram_approval_enabled=False)
    )
    db, thesis_id, ticker = db_thesis
    thesis = db.get(ThesisVersion, thesis_id)
    assert approval.send_thesis_approval_request(db, thesis, ticker)["status"] == "skipped"
    assert _FakePostClient.calls == []


def test_send_not_configured_without_token(monkeypatch, db_thesis):
    _FakePostClient.calls.clear()
    monkeypatch.setattr(approval.httpx, "Client", _FakePostClient)
    monkeypatch.setattr(
        approval,
        "get_settings",
        lambda: _enabled_settings(telegram_bot_token=None, telegram_chat_id=None),
    )
    db, thesis_id, ticker = db_thesis
    thesis = db.get(ThesisVersion, thesis_id)
    result = approval.send_thesis_approval_request(db, thesis, ticker)
    assert result["status"] == "not_configured"
    assert _FakePostClient.calls == []


def test_send_delivered_posts_keyboard_and_marks_pending(monkeypatch, db_thesis):
    _FakePostClient.calls.clear()
    monkeypatch.setattr(approval.httpx, "Client", _FakePostClient)
    monkeypatch.setattr(approval, "get_settings", lambda: _enabled_settings())
    db, thesis_id, ticker = db_thesis
    thesis = db.get(ThesisVersion, thesis_id)
    result = approval.send_thesis_approval_request(db, thesis, ticker)
    assert result["status"] == "delivered"
    url, body = _FakePostClient.calls[0]
    assert url.endswith("/sendMessage")
    assert "test-token" not in body["text"]
    assert ticker in body["text"]
    assert "parse_mode" not in body
    callbacks = [
        b["callback_data"]
        for row in body["reply_markup"]["inline_keyboard"]
        for b in row
    ]
    assert f"thesis:approve:{thesis_id}" in callbacks
    assert f"thesis:reject:{thesis_id}" in callbacks
    section = (
        db.query(ThesisSection)
        .filter(ThesisSection.thesis_version_id == thesis_id)
        .one()
    )
    assert section.section_key == "approval"
    assert section.status == "pending"


def test_send_failure_returns_failed_and_never_raises(monkeypatch, db_thesis):
    monkeypatch.setattr(approval.httpx, "Client", _FailingClient)
    monkeypatch.setattr(approval, "get_settings", lambda: _enabled_settings())
    db, thesis_id, ticker = db_thesis
    thesis = db.get(ThesisVersion, thesis_id)
    result = approval.send_thesis_approval_request(db, thesis, ticker)
    assert result["status"] == "failed"
    assert approval.maybe_request_thesis_approval(db, thesis, ticker) is None


def test_apply_approve_publishes_and_reject_requests_changes(db_thesis):
    db, thesis_id, _ = db_thesis
    thesis = approval.apply_approval_decision(db, thesis_id, "approve")
    assert thesis.status == "published"
    section = (
        db.query(ThesisSection)
        .filter(ThesisSection.thesis_version_id == thesis_id)
        .one()
    )
    assert section.status == "approved"

    # Idempotente: segunda aplicación no duplica ni falla.
    approval.apply_approval_decision(db, thesis_id, "approve")
    assert (
        db.query(ThesisSection)
        .filter(ThesisSection.thesis_version_id == thesis_id)
        .count()
        == 1
    )

    thesis = approval.apply_approval_decision(db, thesis_id, "reject")
    assert thesis.status == "changes_requested"
    db.refresh(section)
    assert section.status == "changes_requested"


def test_apply_unknown_decision_or_thesis_raises(db_thesis):
    db, thesis_id, _ = db_thesis
    with pytest.raises(ValueError):
        approval.apply_approval_decision(db, thesis_id, "publish")
    with pytest.raises(ValueError):
        approval.apply_approval_decision(db, 999999999, "approve")


def test_poll_once_applies_callbacks_and_persists_offset(
    monkeypatch, db_thesis, tmp_path
):
    db, thesis_id, _ = db_thesis
    other_ticker = f"B{uuid4().hex[:8].upper()}"
    other_company = Company(
        ticker=other_ticker,
        name="Approval Test 2",
        exchange="TEST",
        currency="USD",
        sector="Technology",
        industry="Software",
        company_type="operating_company",
        valuation_model="standard_dcf",
        factor_tags=[],
    )
    db.add(other_company)
    db.flush()
    other = ThesisVersion(
        company_id=other_company.id,
        version=1,
        status="draft",
        thesis_markdown="# T2",
        executive_summary="Otra tesis.",
    )
    db.add(other)
    db.commit()
    other_id = other.id

    _FakePollClient.calls.clear()
    _FakePollClient.updates_payload = {
        "ok": True,
        "result": [
            {"update_id": 10, "message": {"text": "ruido"}},
            {
                "update_id": 11,
                "callback_query": {
                    "id": "q-approve",
                    "data": f"thesis:approve:{thesis_id}",
                },
            },
            {
                "update_id": 12,
                "callback_query": {"id": "q-bad", "data": "thesis:approve:999999999"},
            },
            {
                "update_id": 13,
                "callback_query": {"id": "q-reject", "data": f"thesis:reject:{other_id}"},
            },
        ],
    }
    state_file = tmp_path / "offset"
    monkeypatch.setattr(approval.httpx, "Client", _FakePollClient)
    monkeypatch.setattr(
        approval, "get_settings", lambda: _enabled_settings()
    )
    result = approval.poll_telegram_approvals_once(db, state_path=state_file)
    assert result["status"] == "ok"
    assert result["processed"] == 2
    assert result["approved"] == 1
    assert result["rejected"] == 1
    assert result["skipped"] == 2  # mensaje sin callback + tesis inexistente
    assert result["last_update_id"] == 13
    assert state_file.read_text(encoding="utf-8") == "14"
    assert db.get(ThesisVersion, thesis_id).status == "published"
    assert db.get(ThesisVersion, other_id).status == "changes_requested"
    posts = [c for c in _FakePollClient.calls if c[0] == "post"]
    assert any("answerCallbackQuery" in c[1] for c in posts)
    get_calls = [c for c in _FakePollClient.calls if c[0] == "get"]
    assert get_calls and get_calls[0][1].endswith("/getUpdates")

    # Segunda pasada sin novedades: offset reutilizado, nada que procesar.
    _FakePollClient.calls.clear()
    _FakePollClient.updates_payload = {"ok": True, "result": []}
    again = approval.poll_telegram_approvals_once(db, state_path=state_file)
    assert again["processed"] == 0
    sent_offsets = [c[2]["offset"] for c in _FakePollClient.calls if c[0] == "get"]
    assert sent_offsets == [14]

    for section in (
        db.query(ThesisSection)
        .filter(ThesisSection.thesis_version_id == other_id)
        .all()
    ):
        db.delete(section)
    db.delete(db.get(ThesisVersion, other_id))
    db.delete(other_company)
    db.commit()


def test_poll_disabled_does_no_network(monkeypatch, db_thesis, tmp_path):
    _FakePollClient.calls.clear()
    monkeypatch.setattr(approval.httpx, "Client", _FakePollClient)
    monkeypatch.setattr(
        approval, "get_settings", lambda: _enabled_settings(telegram_approval_enabled=False)
    )
    db, _, _ = db_thesis
    result = approval.poll_telegram_approvals_once(
        db, state_path=tmp_path / "offset"
    )
    assert result["status"] == "disabled"
    assert _FakePollClient.calls == []


def test_read_offset_defaults_and_corrupt(tmp_path):
    missing = tmp_path / "no-existe"
    assert approval.read_offset(missing) == 0
    bad = tmp_path / "bad"
    bad.write_text("abc", encoding="utf-8")
    assert approval.read_offset(bad) == 0
    ok = tmp_path / "ok"
    approval.write_offset(ok, 41)
    assert approval.read_offset(ok) == 41
