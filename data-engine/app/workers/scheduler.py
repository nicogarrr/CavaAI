from __future__ import annotations

from functools import partial

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app.workers.dramatiq_app import (
    consolidate_memory,
    evaluate_alert_rules,
    refresh_market_pipeline,
    refresh_ir_pages,
    refresh_news,
    refresh_rss_feeds,
    refresh_sec_filings,
    review_theses,
    run_daily_research,
    dispatch_insider_alerts,
    scan_contradictions,
    scan_insider_watchlist,
    tenant_contexts,
)


JOB_DEFAULTS = {
    "replace_existing": True,
    "max_instances": 1,
    "coalesce": True,
    "misfire_grace_time": 900,
}


def _register(scheduler: BlockingScheduler, func, trigger: str, *, job_id: str, **trigger_args) -> None:
    scheduler.add_job(
        func,
        trigger,
        id=job_id,
        **JOB_DEFAULTS,
        **trigger_args,
    )


def enqueue_insider_scan(*, lookback: int, max_new_fetches: int) -> dict:
    """Fan-out del monitor insider con el alcance propio de cada cadencia."""
    queued = []
    for tenant_id, user_id in tenant_contexts():
        message = scan_insider_watchlist.send(
            tenant_id, user_id, lookback, max_new_fetches
        )
        queued.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message_id": str(message.message_id),
            }
        )
    return {
        "actor": scan_insider_watchlist.actor_name,
        "lookback": lookback,
        "max_new_fetches": max_new_fetches,
        "queued": queued,
    }


def enqueue_for_all_tenants(actor) -> dict:
    queued = []
    for tenant_id, user_id in tenant_contexts():
        message = actor.send(tenant_id, user_id)
        queued.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "message_id": str(message.message_id),
            }
        )
    return {"actor": actor.actor_name, "queued": queued}


def build_scheduler(*, background: bool = False) -> BlockingScheduler | BackgroundScheduler:
    scheduler_cls = BackgroundScheduler if background else BlockingScheduler
    scheduler = scheduler_cls(timezone="UTC")
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, refresh_market_pipeline),
        "interval",
        job_id="market_refresh",
        hours=1,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, refresh_rss_feeds),
        "interval",
        job_id="rss_refresh",
        minutes=15,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, refresh_news),
        "interval",
        job_id="news_refresh",
        minutes=30,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, refresh_ir_pages),
        "interval",
        job_id="ir_refresh",
        hours=1,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, refresh_sec_filings),
        "cron",
        job_id="sec_refresh",
        hour="*/4",
        minute=5,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, scan_contradictions),
        "cron",
        job_id="contradiction_scan",
        hour="*",
        minute=20,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, consolidate_memory),
        "cron",
        job_id="memory_consolidation",
        hour=3,
        minute=15,
    )
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, review_theses),
        "cron",
        job_id="thesis_review",
        hour=7,
        minute=0,
    )
    _register(
        scheduler,
        run_daily_research.send,
        "cron",
        job_id="daily_research",
        hour=6,
        minute=30,
    )
    # PR-3 insider monitor: 15 min durante el dia (jittered), catch-up diario
    # mas profundo tras el cierre de EDGAR, reconciliacion semanal completa.
    _register(
        scheduler,
        partial(enqueue_insider_scan, lookback=20, max_new_fetches=25),
        "interval",
        job_id="insider_watchlist_scan",
        minutes=15,
        jitter=120,
    )
    _register(
        scheduler,
        partial(enqueue_insider_scan, lookback=100, max_new_fetches=60),
        "cron",
        job_id="insider_watchlist_daily",
        hour=22,
        minute=30,
        jitter=300,
    )
    _register(
        scheduler,
        partial(enqueue_insider_scan, lookback=500, max_new_fetches=200),
        "cron",
        job_id="insider_watchlist_weekly",
        day_of_week="sun",
        hour=3,
        minute=45,
    )
    # Evaluacion de reglas de alerta del usuario: barata (una lectura por
    # regla + emision solo al disparar) y con cooldown por regla, asi que
    # cada 5 minutos es seguro. El estado de cada evaluacion queda en
    # AlertRule.last_result y es visible en /alerts.
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, evaluate_alert_rules),
        "interval",
        job_id="alert_rule_evaluation",
        minutes=5,
        jitter=60,
    )
    # PR-4 insider alert outbox: re-evaluacion frecuente es barata porque
    # la dedupe es por fingerprint (rule_version + tx), nunca por ticker.
    _register(
        scheduler,
        partial(enqueue_for_all_tenants, dispatch_insider_alerts),
        "interval",
        job_id="insider_alert_outbox",
        minutes=20,
        jitter=180,
    )
    return scheduler


def main() -> None:
    scheduler = build_scheduler(background=False)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
