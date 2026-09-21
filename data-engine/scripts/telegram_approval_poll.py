"""Poller ligero de aprobación de tesis por Telegram (getUpdates).

Uso desde data-engine/:
    TELEGRAM_APPROVAL_ENABLED=true TELEGRAM_ENABLED=true \\
    TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... \\
        .venv/Scripts/python.exe scripts/telegram_approval_poll.py [--once]

Sin --once, repite ``poll_telegram_approvals_once`` cada
``TELEGRAM_APPROVAL_POLL_INTERVAL_SECONDS`` (defecto 15s). El offset de
getUpdates persiste en ``TELEGRAM_APPROVAL_STATE_PATH``.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

DATA_ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA_ENGINE_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services.thesis_approval_service import (  # noqa: E402
    poll_telegram_approvals_once,
)


def run_once() -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        return poll_telegram_approvals_once(db, settings)


def main(argv: list[str]) -> int:
    once = "--once" in argv
    result = run_once()
    print(result, flush=True)
    if once or result.get("status") in {"disabled", "not_configured"}:
        return 0 if result.get("status") != "failed" else 1
    interval = get_settings().telegram_approval_poll_interval_seconds
    try:
        while True:
            time.sleep(interval)
            print(run_once(), flush=True)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
