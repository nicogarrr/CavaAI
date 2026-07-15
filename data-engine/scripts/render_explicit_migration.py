"""Render frozen Alembic table declarations from the current SQLAlchemy schema.

This is a developer utility: its output is reviewed and committed into a
revision so runtime migrations never import mutable application metadata.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import UniqueConstraint

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: F401
from app.core.database import Base


TABLE_GROUPS = {
    "tenant": {"tenants"},
    "initial": {
        "companies",
        "tenants",
        "positions",
        "cash_balances",
        "transactions",
        "documents",
        "document_chunks",
        "financial_facts",
        "financial_statements",
        "market_prices",
        "news_events",
        "external_claims",
        "transcripts",
        "call_claims",
        "catalysts",
        "valuation_models",
        "valuation_assumptions",
        "valuation_outputs",
        "thesis_versions",
        "thesis_diffs",
        "source_audits",
        "risk_events",
        "daily_briefs",
        "chat_sessions",
        "model_runs",
        "budget_usage",
    },
    "memory": {
        "thesis_sections",
        "claims",
        "claim_evidence",
        "thesis_changes",
        "research_sessions",
        "memory_items",
    },
    "calculated": {"calculated_metrics"},
    "automation": {
        "evidence_suggestions",
        "research_reviews",
        "thesis_nodes",
        "thesis_edges",
        "research_alerts",
        "connector_states",
        "earnings_runs",
        "moat_assessments",
        "peer_relationships",
        "red_team_runs",
    },
}


def _type_expression(column_type: sa.types.TypeEngine) -> str:
    if isinstance(column_type, sa.Text):
        return "sa.Text()"
    if isinstance(column_type, sa.String):
        return f"sa.String({column_type.length})" if column_type.length else "sa.String()"
    if isinstance(column_type, sa.Numeric):
        return f"sa.Numeric({column_type.precision}, {column_type.scale})"
    if isinstance(column_type, sa.DateTime):
        return f"sa.DateTime(timezone={column_type.timezone!r})"
    if isinstance(column_type, sa.Date):
        return "sa.Date()"
    if isinstance(column_type, sa.Boolean):
        return "sa.Boolean()"
    if isinstance(column_type, sa.JSON):
        return "sa.JSON()"
    if isinstance(column_type, sa.Integer):
        return "sa.Integer()"
    raise TypeError(f"Unsupported migration type: {column_type!r}")


def _render_table(table: sa.Table) -> list[str]:
    lines = ["    op.create_table(", f'        "{table.name}",']
    for column in table.columns:
        arguments = [f'"{column.name}"', _type_expression(column.type)]
        foreign_keys = sorted(column.foreign_keys, key=lambda item: item.target_fullname)
        arguments.extend(f'sa.ForeignKey("{item.target_fullname}")' for item in foreign_keys)
        if column.primary_key:
            arguments.append("primary_key=True")
        arguments.append(f"nullable={column.nullable!r}")
        lines.append(f"        sa.Column({', '.join(arguments)}),")

    unique_constraints = sorted(
        (
            constraint
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        ),
        key=lambda item: item.name or "",
    )
    for constraint in unique_constraints:
        columns = ", ".join(f'"{column.name}"' for column in constraint.columns)
        name = f', name="{constraint.name}"' if constraint.name else ""
        lines.append(f"        sa.UniqueConstraint({columns}{name}),")
    lines.append("    )")

    for index in sorted(table.indexes, key=lambda item: item.name or ""):
        index_columns = [column.name for column in index.columns]
        rendered_columns = ", ".join(f'"{name}"' for name in index_columns)
        lines.append(
            f'    op.create_index("{index.name}", "{table.name}", '
            f"[{rendered_columns}], unique={index.unique!r})"
        )
    return lines


def render(group: str) -> str:
    selected = TABLE_GROUPS[group]
    tables = [table for table in Base.metadata.sorted_tables if table.name in selected]
    if {table.name for table in tables} != selected:
        missing = selected - {table.name for table in tables}
        raise RuntimeError(f"Unknown tables: {sorted(missing)}")
    return "\n".join(line for table in tables for line in [*_render_table(table), ""])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=sorted(TABLE_GROUPS))
    arguments = parser.parse_args()
    print(render(arguments.group))
