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
    from sqlalchemy import inspect, text

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight forward-compat for SQLite/dev DBs created before new columns.
    try:
        inspector = inspect(engine)
        if "thesis_versions" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("thesis_versions")}
            if "input_fingerprint" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE thesis_versions ADD COLUMN input_fingerprint VARCHAR(64)")
                    )
        if settings.database_url.startswith("sqlite"):
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
