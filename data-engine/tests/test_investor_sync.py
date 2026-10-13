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
        return {"status": "unavailable"}

    def form4_sync(_db, slug):
        if slug == "bezos":
            raise ValueError("boom")
        return 0

    out = sync_investor_holdings(db, manager_sync=manager_sync, form4_sync=form4_sync)
    assert out["status"] == "partial"
    assert out["managers"][first] == "error"
    assert all(v == "unavailable" for c, v in out["managers"].items() if c != first)
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


def test_actor_is_leased_off_the_alert_queue_and_scheduled_weekly():
    actor = dramatiq_app.sync_investor_holdings
    assert actor.queue_name != "alerts"
    fn = getattr(actor, "fn", actor)
    source = inspect.getsource(fn)
    assert source.index("_session(") < source.index("acquire_job_lease(")
    assert "if lease is None:" in source
    jobs = {job.id: job for job in scheduler.build_scheduler(background=True).get_jobs()}
    job = jobs["investor_holdings_weekly"]
    assert "day_of_week='mon'" in str(job.trigger) or "mon" in str(job.trigger)
