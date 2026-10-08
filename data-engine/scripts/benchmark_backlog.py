"""Synthetic local Redis/Dramatiq benchmark. No production data, DB or LLM.

Starts an ephemeral Redis unix socket; never connects to a supplied account.
Latency is scheduler isolation under controlled sleep jobs, not LLM throughput.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import dramatiq
import redis
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Retries
from dramatiq.worker import Worker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.workers.bounded_broker import BoundedRedisBroker, QueueCapacityError  # noqa: E402


def run_case(client, isolated):
    client.flushdb()  # ONLY the disposable Redis started in main
    broker = (BoundedRedisBroker if isolated else RedisBroker)(client=client, middleware=[Retries()])
    started = time.monotonic()
    alert_latency = []

    def kpi_job():
        time.sleep(0.04)

    def alert_job():
        alert_latency.append(time.monotonic() - started)

    kpi = dramatiq.actor(kpi_job, broker=broker, queue_name="kpis" if isolated else "default")
    alert = dramatiq.actor(alert_job, broker=broker, queue_name="alerts" if isolated else "default")
    os.environ["KPI_QUEUE_MAX_PENDING"] = "20"

    def submit(_):
        try:
            kpi.send()
            return 1
        except QueueCapacityError:
            return 0

    with ThreadPoolExecutor(16) as pool:
        admitted = sum(pool.map(submit, range(80)))
    alert.send()
    alert_broker = RedisBroker(client=client, middleware=[Retries()])
    alert_broker.declare_actor(alert)
    workers = (
        [Worker(broker, queues={"kpis"}, worker_threads=4, worker_timeout=20),
         Worker(alert_broker, queues={"alerts"}, worker_threads=1, worker_timeout=20)]
        if isolated else [Worker(broker, queues={"default"}, worker_threads=4, worker_timeout=20)]
    )
    started = time.monotonic()
    try:
        for worker in workers:
            worker.start()
        for queue in broker.get_declared_queues():
            broker.join(queue, interval=10, timeout=10000)
        elapsed = time.monotonic() - started
    finally:
        for worker in workers:
            worker.stop(timeout=5000)
    return {"submitted_kpi": 80, "admitted_kpi": admitted,
            "deferred_kpi": 80 - admitted, "threads": 5 if isolated else 4,
            "alert_latency_ms": round(alert_latency[0] * 1000, 2),
            "admitted_batch_drain_ms": round(elapsed * 1000, 2)}


def main():
    binary = shutil.which("redis-server")
    if not binary:
        raise SystemExit("Instala redis-server para el benchmark local")
    with tempfile.TemporaryDirectory(prefix="cavaai-bench-") as tmp:
        socket = str(Path(tmp) / "redis.sock")
        process = subprocess.Popen(
            [binary, "--port", "0", "--unixsocket", socket, "--save", "", "--appendonly", "no"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        client = redis.Redis(unix_socket_path=socket)
        try:
            for _ in range(100):
                try:
                    if client.ping():
                        break
                except redis.RedisError:
                    time.sleep(0.04)
            else:
                raise RuntimeError("Redis local no arranco")
            print(json.dumps({"kind": "synthetic_local_not_production",
                              "dramatiq": dramatiq.__version__,
                              "redis": client.info("server")["redis_version"],
                              "shared": run_case(client, False),
                              "isolated_bounded": run_case(client, True)}, indent=2))
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()
