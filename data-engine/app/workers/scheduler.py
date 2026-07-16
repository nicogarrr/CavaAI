from __future__ import annotations

from functools import partial

from apscheduler.schedulers.blocking import BlockingScheduler

from app.workers.dramatiq_app import (
    consolidate_memory,
    refresh_market_pipeline,
    refresh_ir_pages,
    refresh_news,
    refresh_rss_feeds,
    refresh_sec_filings,
    review_theses,
    run_daily_research,
    scan_contradictions,
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


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="UTC")
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
    return scheduler


def main() -> None:
    scheduler = build_scheduler()
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
