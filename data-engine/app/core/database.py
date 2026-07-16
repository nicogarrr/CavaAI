from collections.abc import Generator

from fastapi import Depends
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker, with_loader_criteria

from app.core.auth import ResearchPrincipal, get_research_principal
from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@event.listens_for(Session, "do_orm_execute")
def _scope_tenant_queries(execute_state) -> None:
    if (
        not execute_state.is_select
        or execute_state.execution_options.get("include_all_tenants")
    ):
        return
    tenant_id = execute_state.session.info.get("tenant_id")
    if tenant_id is None:
        return
    from app.models.entities import TenantOwnedMixin

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantOwnedMixin,
            lambda model: model.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _assign_tenant_to_new_rows(session: Session, _flush_context, _instances) -> None:
    tenant_id = session.info.get("tenant_id")
    from app.models.entities import TenantOwnedMixin

    tenant_rows = [instance for instance in session.new if isinstance(instance, TenantOwnedMixin)]
    if tenant_id is None:
        if settings.research_auth_required and tenant_rows:
            raise RuntimeError("Tenant context is required for tenant-owned writes")
        return

    for instance in tenant_rows:
        if instance.tenant_id is None:
            instance.tenant_id = tenant_id
        elif instance.tenant_id != tenant_id:
            raise RuntimeError("Cross-tenant writes are not allowed")


def get_db(
    principal: ResearchPrincipal | None = Depends(get_research_principal),
) -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        if principal:
            from app.models import Tenant

            tenant = db.scalar(
                select(Tenant).where(
                    Tenant.external_id == principal.tenant_external_id
                )
            )
            if tenant is None:
                tenant = Tenant(
                    external_id=principal.tenant_external_id,
                    name=f"Workspace {principal.tenant_external_id[:80]}",
                    metadata_={"created_by": principal.user_id},
                )
                db.add(tenant)
                db.commit()
                db.refresh(tenant)
            db.info["tenant_id"] = tenant.id
            db.info["user_id"] = principal.user_id
        yield db
    finally:
        db.close()


def init_db() -> None:
    import re

    from sqlalchemy import inspect, text

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight forward-compat for SQLite/dev DBs created before new columns.
    try:
        inspector = inspect(engine)
        if settings.database_url.startswith("sqlite") and "investment_principles" in (
            inspector.get_table_names()
        ):
            principle_columns = {
                column["name"]
                for column in inspector.get_columns("investment_principles")
            }
            principle_additions = {
                "principle_fingerprint": "VARCHAR(64)",
                "semantic_duplicate_of_id": "INTEGER",
                "canonical_principle_id": "INTEGER",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "superseded_by_id": "INTEGER",
            }
            with engine.begin() as conn:
                for column, definition in principle_additions.items():
                    if column not in principle_columns:
                        conn.execute(
                            text(
                                "ALTER TABLE investment_principles "
                                f"ADD COLUMN {column} {definition}"
                            )
                        )
                conn.execute(
                    text(
                        "UPDATE investment_principles "
                        "SET principle_fingerprint = lower(hex(randomblob(32))) "
                        "WHERE principle_fingerprint IS NULL"
                    )
                )
        if "thesis_versions" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("thesis_versions")}
            if "input_fingerprint" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE thesis_versions ADD COLUMN input_fingerprint VARCHAR(64)")
                    )
        if settings.database_url.startswith("sqlite"):
            thesis_columns = {
                column["name"]: column
                for column in inspector.get_columns("thesis_versions")
            }
            nullable_thesis_values = (
                "current_price",
                "bear_value",
                "base_value",
                "bull_value",
                "expected_value",
                "margin_of_safety",
            )
            if any(
                not thesis_columns[column]["nullable"]
                for column in nullable_thesis_values
                if column in thesis_columns
            ):
                # SQLite cannot drop NOT NULL in place. Rebuild only this table,
                # preserving its constraints, data and explicit indexes.
                with engine.connect() as conn:
                    create_sql = conn.execute(
                        text(
                            "SELECT sql FROM sqlite_master "
                            "WHERE type='table' AND name='thesis_versions'"
                        )
                    ).scalar_one()
                    index_sql = [
                        row[0]
                        for row in conn.execute(
                            text(
                                "SELECT sql FROM sqlite_master WHERE type='index' "
                                "AND tbl_name='thesis_versions' AND sql IS NOT NULL"
                            )
                        ).all()
                    ]
                    conn.commit()
                    conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
                    conn.commit()
                    try:
                        with conn.begin():
                            rebuilt = create_sql.replace(
                                "CREATE TABLE thesis_versions",
                                "CREATE TABLE thesis_versions__nullable",
                                1,
                            )
                            for column in nullable_thesis_values:
                                rebuilt = re.sub(
                                    rf"(\b{column}\b\s+NUMERIC\([^)]+\))\s+NOT NULL",
                                    r"\1",
                                    rebuilt,
                                    count=1,
                                    flags=re.IGNORECASE,
                                )
                            conn.exec_driver_sql(rebuilt)
                            names = [
                                row[1]
                                for row in conn.exec_driver_sql(
                                    "PRAGMA table_info(thesis_versions)"
                                ).all()
                            ]
                            quoted = ", ".join(f'"{name}"' for name in names)
                            conn.exec_driver_sql(
                                f"INSERT INTO thesis_versions__nullable ({quoted}) "
                                f"SELECT {quoted} FROM thesis_versions"
                            )
                            conn.exec_driver_sql("DROP TABLE thesis_versions")
                            conn.exec_driver_sql(
                                "ALTER TABLE thesis_versions__nullable "
                                "RENAME TO thesis_versions"
                            )
                            for statement in index_sql:
                                conn.exec_driver_sql(statement)
                    finally:
                        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
                        conn.commit()
                inspector = inspect(engine)
            sqlite_forward_columns = {
                "positions": {
                    "portfolio_id": "INTEGER",
                    "base_currency": "VARCHAR(10) NOT NULL DEFAULT 'EUR'",
                    "market_value_native": "NUMERIC(24, 6)",
                    "market_value_base": "NUMERIC(24, 6)",
                    "cost_basis_native": "NUMERIC(24, 6)",
                    "cost_basis_base": "NUMERIC(24, 6)",
                    "unrealized_pnl_base": "NUMERIC(24, 6)",
                    "realized_pnl_base": "NUMERIC(24, 6)",
                    "fx_rate": "NUMERIC(20, 10)",
                },
                "transactions": {"portfolio_id": "INTEGER"},
                "fundamental_model_versions": {
                    "algorithm_version": "VARCHAR(160) NOT NULL DEFAULT 'unknown'",
                    "forecast_fingerprint": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                    "market_snapshot_fingerprint": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                    "valuation_snapshot_fingerprint": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                    "code_commit_sha": "VARCHAR(80) NOT NULL DEFAULT 'unknown'",
                },
                "expectation_reviews": {
                    "actual_metric_id": "INTEGER",
                    "actual_source_type": "VARCHAR(40)",
                    "semantics": "VARCHAR(40) NOT NULL DEFAULT 'higher_is_better'",
                },
                "fundamental_drivers": {
                    "currency": "VARCHAR(10) NOT NULL DEFAULT 'N/A'",
                    "time_basis": "VARCHAR(40) NOT NULL DEFAULT 'point_in_time'",
                    "geography": "VARCHAR(120) NOT NULL DEFAULT 'global'",
                    "segment": "VARCHAR(160) NOT NULL DEFAULT 'consolidated'",
                    "period": "VARCHAR(40) NOT NULL DEFAULT 'unknown'",
                    "source": "VARCHAR(240) NOT NULL DEFAULT 'financial_fact'",
                },
            }
            table_names = set(inspector.get_table_names())
            for table_name, definitions in sqlite_forward_columns.items():
                if table_name not in table_names:
                    continue
                existing = {
                    column["name"] for column in inspector.get_columns(table_name)
                }
                for column_name, definition in definitions.items():
                    if column_name in existing:
                        continue
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                f'ALTER TABLE "{table_name}" ADD COLUMN '
                                f'"{column_name}" {definition}'
                            )
                        )
                inspector = inspect(engine)
            tenant_tables = [
                table.name
                for table in Base.metadata.sorted_tables
                if "tenant_id" in table.columns
                and table.name in inspector.get_table_names()
            ]
            for table_name in tenant_tables:
                columns = {
                    col["name"]
                    for col in inspector.get_columns(table_name)
                }
                if "tenant_id" not in columns:
                    with engine.begin() as conn:
                        conn.execute(
                            text(
                                f'ALTER TABLE "{table_name}" '
                                "ADD COLUMN tenant_id INTEGER"
                            )
                        )
                    inspector = inspect(engine)
    except Exception:  # noqa: BLE001 — never block startup on optional alter
        pass
