from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Iterator

from app.core.config import get_settings


@dataclass
class TraceHandle:
    """Local trace mirror; it remains inspectable when Langfuse is disabled."""

    name: str
    metadata: dict[str, Any] = field(default_factory=dict)
    output: Any = None
    error: str | None = None

    def update(self, **metadata: Any) -> None:
        self.metadata.update(metadata)


class LangfuseTracer:
    def __init__(self) -> None:
        self.settings = get_settings()

    @contextmanager
    def workflow(
        self, name: str, metadata: dict[str, Any] | None = None
    ) -> Iterator[TraceHandle]:
        started = perf_counter()
        handle = TraceHandle(name=name, metadata=dict(metadata or {}))
        client = None
        remote_trace = None
        if self.settings.langfuse_enabled:
            try:
                from langfuse import Langfuse

                client = Langfuse(
                    public_key=self.settings.langfuse_public_key,
                    secret_key=self.settings.langfuse_secret_key,
                    host=self.settings.langfuse_host,
                )
                remote_trace = client.trace(name=name, metadata=handle.metadata)
            except Exception as exc:  # observability must not break analysis
                handle.metadata["telemetry_setup_error"] = type(exc).__name__
        try:
            yield handle
        except Exception as exc:
            handle.error = type(exc).__name__
            raise
        finally:
            handle.metadata["latency_ms"] = round((perf_counter() - started) * 1000, 3)
            if remote_trace is not None:
                try:
                    remote_trace.update(
                        metadata=handle.metadata,
                        output=handle.output,
                        status_message=handle.error,
                    )
                    client.flush()
                except Exception as exc:  # keep a visible local failure counter
                    handle.metadata["telemetry_flush_error"] = type(exc).__name__
