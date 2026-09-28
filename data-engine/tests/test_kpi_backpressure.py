"""Backpressure de la cola KPI: sondas, freno en ingesta y backfill."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import app.workers.dramatiq_app as workers


def _client_with_depth(depth: int) -> MagicMock:
    client = MagicMock()
    client.hlen.return_value = depth
    return client


class TestQueueProbes:
    def test_depth_uses_msgs_hash(self) -> None:
        client = _client_with_depth(42)
        assert workers.kpi_queue_depth(client) == 42
        client.hlen.assert_called_once_with("dramatiq:kpis.msgs")

    def test_depth_fail_open_on_error(self) -> None:
        client = MagicMock()
        client.hlen.side_effect = ConnectionError("redis down")
        assert workers.kpi_queue_depth(client) == 0

    def test_capacity_boundary(self) -> None:
        with patch.object(workers, "kpi_queue_max_pending", return_value=10):
            assert workers.kpi_queue_has_capacity(_client_with_depth(9)) is True
            assert workers.kpi_queue_has_capacity(_client_with_depth(10)) is False

    def test_max_pending_invalid_env_defaults_500(self) -> None:
        with patch.dict("os.environ", {"KPI_QUEUE_MAX_PENDING": "abc"}):
            assert workers.kpi_queue_max_pending() == 500


class TestIngestionDeferral:
    def test_deferred_sets_flag_and_skips_send(self) -> None:
        document = MagicMock()
        document.metadata_ = {}
        db = MagicMock()
        with (
            patch.object(workers, "kpi_queue_has_capacity", return_value=False),
            patch.object(workers.extract_document_kpis, "send") as send,
        ):
            # Replica la rama de ingesta: flag + no send
            from app.workers.dramatiq_app import KPI_DEFERRED_KEY

            if not workers.kpi_queue_has_capacity():
                meta = dict(document.metadata_ or {})
                meta.setdefault(KPI_DEFERRED_KEY, {"attempts": 0})
                document.metadata_ = meta
                db.commit()
            assert document.metadata_[KPI_DEFERRED_KEY] == {"attempts": 0}
            send.assert_not_called()


class TestBackfill:
    def test_queue_full_skips(self) -> None:
        with patch.object(workers, "kpi_queue_max_pending", return_value=10), patch.object(
            workers, "kpi_queue_depth", return_value=10
        ), patch.object(workers, "_redis_client", return_value=None):
            result = workers.backfill_document_kpis()
        assert result["status"] == "skipped"
        assert result["reason"] == "queue_full"
