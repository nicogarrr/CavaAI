"""Refresco semanal de inversores: hermetico (sin red), un fallo no frena al resto."""

import inspect

from app.services.investor_portfolio import FORM4_FILER_CIK
from app.services.investor_sync import sync_investor_holdings
from app.services.manager_holding_ingestion_service import REVIEWED_MANAGERS
from app.workers import dramatiq_app, scheduler


class _Db:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def test_all_managers_and_filers_are_synced_and_reported():
    seen_m, seen_f = [], []
    db = _Db()
    out = sync_investor_holdings(
        db,
        manager_sync=lambda _db, cik: seen_m.append(cik) or {"status": "ok"},
        form4_sync=lambda _db, slug: seen_f.append(slug) or 3,
    )
    assert seen_m == list(REVIEWED_MANAGERS)
    assert seen_f == sorted(FORM4_FILER_CIK)
    assert out["status"] == "ok" and out["errors"] == []
    assert set(out["managers"]) == set(REVIEWED_MANAGERS)
    assert out["form4_new_movements"] == dict.fromkeys(FORM4_FILER_CIK, 3)
    assert db.rollbacks == 0


def test_one_failure_does_not_stop_the_rest_and_is_visible():
    first = next(iter(REVIEWED_MANAGERS))
    db = _Db()

    def manager_sync(_db, cik):
        if cik == first:
            raise RuntimeError("SEC 503")
        return {"status": "ok"}

    def form4_sync(_db, slug):
        if slug == "bezos":
            raise ValueError("boom")
        return 0

    out = sync_investor_holdings(db, manager_sync=manager_sync, form4_sync=form4_sync)
    assert out["status"] == "partial"
    assert out["managers"][first] == "error"
    assert all(v == "ok" for c, v in out["managers"].items() if c != first)
    assert out["form4_new_movements"] == {"trump": 0}
    sources = [e["source"] for e in out["errors"]]
    assert sources == [f"13f:{first}", "form4:bezos"]
    assert "SEC 503" in out["errors"][0]["error"]
    assert db.rollbacks == 2


def test_everything_failing_is_error_not_partial():
    def boom(*_a):
        raise RuntimeError("down")

    out = sync_investor_holdings(_Db(), manager_sync=boom, form4_sync=boom)
    assert out["status"] == "error"
    assert len(out["errors"]) == len(REVIEWED_MANAGERS) + len(FORM4_FILER_CIK)


def test_unavailable_without_exception_is_a_failure_not_ok():
    # sync_manager no lanza cuando la SEC cae: devuelve status "unavailable".
    out = sync_investor_holdings(
        _Db(),
        manager_sync=lambda _db, _cik: {"status": "unavailable", "reason": "SEC 503"},
        form4_sync=lambda _db, _slug: 0,
    )
    assert out["status"] == "partial"  # Form 4 si funciono
    assert len(out["errors"]) == len(REVIEWED_MANAGERS)
    assert out["errors"][0]["error"] == "unavailable: SEC 503"
    assert all(e["source"].startswith("13f:") for e in out["errors"])


def test_everything_unavailable_without_exceptions_is_error():
    def down(*_a):
        return {"status": "unavailable", "reason": "SEC caida"}

    out = sync_investor_holdings(
        _Db(), manager_sync=down, form4_sync=lambda *_a: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert out["status"] == "error"


def test_one_manager_unavailable_is_partial_and_unreviewed_also_counts():
    first, second, *_ = list(REVIEWED_MANAGERS)

    def manager_sync(_db, cik):
        if cik == first:
            return {"status": "unavailable", "reason": "no 13F-HR filings found"}
        if cik == second:
            return {"status": "unreviewed_manager"}
        return {"status": "ok"}

    out = sync_investor_holdings(_Db(), manager_sync=manager_sync, form4_sync=lambda *_a: 1)
    assert out["status"] == "partial"
    assert [e["source"] for e in out["errors"]] == [f"13f:{first}", f"13f:{second}"]
    assert out["errors"][1]["error"].startswith("unreviewed_manager")


def test_actor_is_leased_and_off_the_alert_queue():
    actor = dramatiq_app.sync_investor_holdings
    assert actor.queue_name != "alerts"
    source = inspect.getsource(getattr(actor, "fn", actor))
    assert source.index("_session(") < source.index("acquire_job_lease(")
    assert "if lease is None:" in source


def test_weekly_job_runs_monday_0420_utc():
    job = {j.id: j for j in scheduler.build_scheduler(background=True).get_jobs()}["investor_holdings_weekly"]
    fields = {f.name: str(f) for f in job.trigger.fields}
    assert fields["day_of_week"] == "mon"
    assert fields["hour"] == "4"
    assert fields["minute"] == "20"


def test_exception_text_in_errors_is_redacted_and_bounded():
    def boom(*_a):
        raise RuntimeError("fail https://x.example/api?apikey=SECRETVALUE " + "y" * 500)

    out = sync_investor_holdings(_Db(), manager_sync=boom, form4_sync=boom)
    for err in out["errors"]:
        assert "SECRETVALUE" not in err["error"]
        assert len(err["error"]) <= 200
