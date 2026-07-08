from apscheduler.schedulers.background import BackgroundScheduler

from app.workers.dramatiq_app import run_daily_research


def build_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(run_daily_research.send, "cron", hour=6, minute=30, id="daily_research")
    return scheduler

