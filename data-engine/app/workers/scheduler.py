from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from app.workers.dramatiq_app import (
    consolidate_memory,
    refresh_ir_pages,
    refresh_news,
    refresh_rss_feeds,
    refresh_sec_filings,
    review_theses,
    run_daily_research,
    scan_contradictions,
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


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="UTC")
    _register(
        scheduler,
        refresh_rss_feeds.send,
        "interval",
        job_id="rss_refresh",
        minutes=15,
    )
    _register(
        scheduler,
        refresh_news.send,
        "interval",
        job_id="news_refresh",
        minutes=30,
    )
    _register(
        scheduler,
        refresh_ir_pages.send,
        "interval",
        job_id="ir_refresh",
        hours=1,
    )
    _register(
        scheduler,
        refresh_sec_filings.send,
        "cron",
        job_id="sec_refresh",
        hour="*/4",
        minute=5,
    )
    _register(
        scheduler,
        scan_contradictions.send,
        "cron",
        job_id="contradiction_scan",
        hour="*",
        minute=20,
    )
    _register(
        scheduler,
        consolidate_memory.send,
        "cron",
        job_id="memory_consolidation",
        hour=3,
        minute=15,
    )
    _register(
        scheduler,
        review_theses.send,
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

