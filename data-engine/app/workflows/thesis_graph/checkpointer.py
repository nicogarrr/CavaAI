"""Checkpointer factories and thread-id helper for the thesis graph.

Prod uses PostgresSaver against the existing Postgres (control state only,
in its own tables; business source of truth stays in the domain schema).
Tests use SqliteSaver. No LangGraph Platform/Agent Server is deployed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager


def thesis_thread_id(tenant_id: str, company_id: str, input_fingerprint: str) -> str:
    """Stable thread id: a Dramatiq retry resumes instead of duplicating."""
    return f"thesis:{tenant_id}:{company_id}:{input_fingerprint}"


@contextmanager
def sqlite_checkpointer(path: str = ":memory:") -> Iterator:
    """SqliteSaver for tests/local runs. Yields an initialized saver."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    with SqliteSaver.from_conn_string(path) as saver:
        yield saver


@contextmanager
def postgres_checkpointer(conn_string: str) -> Iterator:
    """PostgresSaver for prod. Caller passes a connection string for the
    existing Postgres; tables are created by setup() on first use."""
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(conn_string) as saver:
        saver.setup()
        yield saver
