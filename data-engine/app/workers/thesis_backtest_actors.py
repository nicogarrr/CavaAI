"""Dramatiq actor for thesis backtest grids.

Lives in its own module rather than in ``app/workers/dramatiq_app.py`` to keep
the diff off a file that many other changes touch. The broker is imported, not
reconfigured, so this module registers an actor and nothing else.

INTEGRACIÓN PENDIENTE: a Dramatiq worker only executes actors that were imported
at boot. Add to ``app/workers/dramatiq_app.py``::

    import app.workers.thesis_backtest_actors  # noqa: F401  (registra el actor)

Without that line the actor is dispatchable but never consumed, and the run row
sits in ``queued`` forever instead of failing loudly — which is exactly why it is
listed as pending integration rather than silently assumed.
"""

from __future__ import annotations

from typing import Any

import dramatiq

# Reuses the broker configured by the worker module. Importing it also performs
# the module-level `dramatiq.set_broker`, so this actor is bound to the same
# broker as every other job.
from app.workers.dramatiq_app import broker as _broker  # noqa: F401


@dramatiq.actor(max_retries=2, min_backoff=30_000, queue_name="backtests")
def run_thesis_backtest_job(run_id: int) -> dict[str, Any]:
    """Execute one queued backtest grid.

    ``max_retries=2``: the grid is idempotent at the cell level (the
    ``(tenant, run, ticker, as_of)`` unique constraint updates instead of
    duplicating), so a retry after a partial run resumes safely rather than
    producing a second, subtly different set of numbers.
    """
    from app.services.thesis_backtest_job_service import execute

    return execute(run_id)
