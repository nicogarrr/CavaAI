"""Atomic admission of new KPI work, using Dramatiq 1.x Redis wire format.

Retries/promotions retain their normal broker path: admission must never discard
an already accepted job. Ready and delayed hashes include unacknowledged work.
"""
from __future__ import annotations

import os
from uuid import uuid4

from dramatiq.brokers.redis import RedisBroker


class QueueCapacityError(RuntimeError):
    """The document must remain deferred in Postgres, not be dropped."""


def max_pending() -> int:
    try:
        return max(1, int(os.getenv("KPI_QUEUE_MAX_PENDING", "500")))
    except ValueError:
        return 500


_ADMIT = """
local depth = redis.call('hlen', KEYS[1]) + redis.call('hlen', KEYS[2])
if depth >= tonumber(ARGV[1]) then return 0 end
redis.call('hset', KEYS[1], ARGV[2], ARGV[3])
redis.call('rpush', KEYS[3], ARGV[2])
return 1
"""


class BoundedRedisBroker(RedisBroker):
    def enqueue(self, message, *, delay=None):
        # DQ promotions carry eta; retry messages carry retries. Neither is
        # new ingestion, and blocking either would lose accepted work.
        if (message.queue_name != "kpis" or delay is not None
                or "retries" in message.options or "eta" in message.options):
            return super().enqueue(message, delay=delay)
        message = message.copy(options={"redis_message_id": str(uuid4())})
        self.emit_before("enqueue", message, delay)
        base = f"{self.namespace}:kpis"
        admitted = self.client.eval(
            _ADMIT, 3, f"{base}.msgs", f"{base}.DQ.msgs", base,
            max_pending(), message.options["redis_message_id"], message.encode(),
        )
        if not admitted:
            raise QueueCapacityError("La cola KPI esta llena; documento diferido")
        self.emit_after("enqueue", message, delay)
        return message
