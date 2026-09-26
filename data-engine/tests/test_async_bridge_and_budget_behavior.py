"""Tests de comportamiento del puente sync/async y del presupuesto por tenant.

Complementan a test_async_bridge_and_tenant_budget.py (guardas de codigo) con
pruebas que ejecutan los caminos reales: concurrencia, reentrada y aislamiento
entre dos tenants.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.entities import Base, BudgetUsage
from app.services.async_bridge import run_from_any_context
from app.services.budget import BudgetController


async def _value(i: int) -> int:
    await asyncio.sleep(0.01)
    return i


def test_bridge_concurrent_callers_all_get_their_own_result():
    """16 llamadas concurrentes desde hilos sync: sin mezcla ni perdida."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda i: run_from_any_context(_value(i)), range(16))
        )
    assert sorted(results) == list(range(16))


def test_bridge_from_loop_via_to_thread_keeps_the_loop_pumping():
    """Patron recomendado (to_thread): el loop sigue atendiendo otras tareas."""
    ticks = 0

    async def ticker(stop: list[bool]) -> None:
        nonlocal ticks
        while not stop[0]:
            ticks += 1
            await asyncio.sleep(0.005)

    async def slow() -> str:
        await asyncio.sleep(0.15)
        return "done"

    async def main() -> str:
        stop = [False]
        tick_task = asyncio.create_task(ticker(stop))
        try:
            return await asyncio.to_thread(run_from_any_context, slow())
        finally:
            stop[0] = True
            await tick_task

    assert asyncio.run(main()) == "done"
    # Si el loop hubiera quedado bloqueado por la espera, el ticker no avanza.
    assert ticks >= 10


def test_bridge_reentrancy_from_bridge_thread_fails_loudly():
    """Anidar el puente desde un hilo puente lanzaria deadlock: debe fallar."""

    async def outer() -> str:
        # Estamos en el hilo puente con un loop activo: la reentrada no puede
        # hacer otro submit; tiene que lanzar en vez de arriesgar un deadlock.
        run_from_any_context(_value(1))
        return "unreachable"

    async def main() -> str:
        # Llamar desde un loop activo envia outer() al hilo puente.
        return run_from_any_context(outer())

    with pytest.raises(RuntimeError, match="no puede anidarse"):
        asyncio.run(main())


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed_budget(db, tenant_id: int, cost: str) -> None:
    db.add(
        BudgetUsage(
            tenant_id=tenant_id,
            usage_date=date.today(),
            model="deepseek-v4-flash",
            workflow="test",
            cost_eur=Decimal(cost),
            token_count=1000,
        )
    )
    db.commit()


def _session_for(factory, tenant_id):
    db = factory()
    db.info["tenant_id"] = tenant_id
    return db


def test_current_usage_isolates_two_tenants(session_factory):
    _seed_budget(_session_for(session_factory, 1), 1, "1.20")
    _seed_budget(_session_for(session_factory, 2), 2, "0.10")

    usage_1 = BudgetController().current_usage(_session_for(session_factory, 1))
    usage_2 = BudgetController().current_usage(_session_for(session_factory, 2))

    assert usage_1["daily_cost_eur"] == pytest.approx(1.20)
    assert usage_1["tenant_scoped"] is True
    assert usage_2["daily_cost_eur"] == pytest.approx(0.10)
    assert usage_2["tenant_scoped"] is True


def test_can_spend_blocked_tenant_does_not_block_the_other(session_factory):
    controller = BudgetController()
    cap = controller.settings.llm_daily_cap_eur
    # El tenant 1 agota (y supera) el tope diario; el tenant 2 no ha gastado.
    _seed_budget(_session_for(session_factory, 1), 1, f"{cap + 1:.2f}")

    assert controller.can_spend(_session_for(session_factory, 1), 0.01) is False
    assert controller.can_spend(_session_for(session_factory, 2), 0.01) is True


def test_current_usage_without_tenant_context_fails_closed(session_factory):
    db = session_factory()  # sin db.info["tenant_id"]
    with pytest.raises(RuntimeError, match="contexto de tenant"):
        BudgetController().current_usage(db)
    # La vista de operacion consciente sigue disponible y se declara global.
    global_usage = BudgetController().current_usage(db, admin=True)
    assert global_usage["tenant_scoped"] is False


def test_ingest_file_endpoint_runs_sync_ingestion_off_the_loop_thread(monkeypatch):
    """La ruta async no ejecuta la ingesta sync en el hilo del event loop."""
    from app.api.routes import sources

    captured: dict[str, object] = {}

    class _FakeIngestion:
        def ingest_bytes(self, db, **_kwargs):
            captured["thread"] = threading.current_thread()
            captured["has_running_loop"] = False
            try:
                asyncio.get_running_loop()
                captured["has_running_loop"] = True
            except RuntimeError:
                pass
            return {"status": "ok"}

    class _FakeUpload:
        filename = "doc.pdf"
        content_type = "application/pdf"

        async def read(self, _n: int) -> bytes:
            return b""

    monkeypatch.setattr(sources, "DocumentIngestionService", lambda: _FakeIngestion())
    loop_thread = threading.current_thread()

    result = asyncio.run(
        sources.ingest_document_file(
            ticker="AAPL",
            title="Documento de prueba",
            source_type="manual_upload",
            source_url=None,
            file=_FakeUpload(),
            db=None,
        )
    )

    assert result == {"status": "ok"}
    assert captured["thread"] is not loop_thread
    assert captured["has_running_loop"] is False
