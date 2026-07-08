import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings

settings = get_settings()
broker = RedisBroker(url=settings.redis_url)
dramatiq.set_broker(broker)


@dramatiq.actor
def run_daily_research() -> dict:
    return {"status": "queued", "workflow": "DailyResearchWorkflow"}


if __name__ == "__main__":
    print("Dramatiq actors registered. Run with: dramatiq app.workers.dramatiq_app")

