"""El puente sync/async y el presupuesto de LLM por tenant.

Dos fallos silenciosos:

1. `asyncio.run()` lanza RuntimeError cuando ya hay un event loop activo en el
   hilo. Los callers de los helpers Jev (triaje de urgencia, tipo documental,
   gates de noticias, OIR de CNMV) lo envuelven en `except Exception`, de modo
   que la funcion NUNCA se ejecutaba desde ninguna ruta async -ingesta de
   documentos, ingesta de noticias, workers, rutas de documentos- y ademas se
   persistia el RuntimeError en los metadatos. El coste por MTok que describian
   los docstrings nunca seurrency.

2. BudgetController.current_usage sumaba TODO budget_usage sin filtrar por
   tenant. BudgetUsage es TenantOwnedMixin, y un `select(sum(col))` de una sola
   columna no dispara el with_loader_criteria de database.py, asi que el total
   era global: un tenant podia agotar el tope diario de todos los demas, y
   ningun tenant veia su propio gasto.
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.async_bridge import run_from_any_context

# --------------------------------------------------------------------------
# 1. El puente funciona desde sync y desde async
# --------------------------------------------------------------------------


def test_bridge_works_from_sync_context():
    async def value() -> int:
        return 7

    assert run_from_any_context(value()) == 7


def test_bridge_works_from_inside_a_running_loop():
    """Este es el caso que fallaba: hay loop activo en el hilo."""

    async def inner() -> str:
        return "ok"

    async def outer() -> str:
        # Si se usara asyncio.run aqui, lanzaria
        # "asyncio.run() cannot be called from a running event loop".
        return run_from_any_context(inner())

    assert asyncio.run(outer()) == "ok"


def test_bridge_works_from_inside_a_running_loop_in_a_task():
    async def inner() -> int:
        await asyncio.sleep(0)
        return 42

    async def outer() -> int:
        return run_from_any_context(inner())

    assert asyncio.run(outer()) == 42


def test_bridge_propagates_exceptions():
    async def boom() -> None:
        raise ValueError("fallo propagado")

    with pytest.raises(ValueError, match="fallo propagado"):
        run_from_any_context(boom())

    async def outer() -> None:
        run_from_any_context(boom())

    with pytest.raises(ValueError, match="fallo propagado"):
        asyncio.run(outer())


def test_bridge_nested_loops_do_not_deadlock():
    """Un puente dentro de otro puente (sync -> bridge -> loop -> sync -> bridge)."""

    async def deep() -> int:
        return 1

    async def shallow() -> int:
        return run_from_any_context(deep())

    def sync_outer() -> int:
        return run_from_any_context(shallow())

    assert sync_outer() == 1


def test_no_module_uses_raw_asyncio_run_outside_the_bridge():
    """Guarda: `asyncio.run` solo puede existir dentro del puente compartido."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    bridge = root / "services" / "async_bridge.py"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path == bridge or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
            ):
                offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert offenders == [], (
        "asyncio.run() fuera del puente: lanza RuntimeError si hay un loop "
        f"activo y los callers lo silencian. {offenders}"
    )


# --------------------------------------------------------------------------
# 2. El presupuesto se contabiliza por tenant
# --------------------------------------------------------------------------


def test_budget_usage_is_tenant_scoped():
    from app.models import BudgetUsage
    from app.models.entities import TenantOwnedMixin

    assert issubclass(BudgetUsage, TenantOwnedMixin)


def test_current_usage_filters_by_tenant():
    import inspect

    from app.services.budget import BudgetController

    source = inspect.getsource(BudgetController.current_usage)
    assert "BudgetUsage.tenant_id" in source, (
        "current_usage suma todo budget_usage sin filtrar por tenant: un solo "
        "tenant agota el tope diario de todos los demas"
    )
    assert "db.info.get(\"tenant_id\")" in source


def test_knowledge_principles_batches_go_through_the_budget():
    import inspect

    from app.services.knowledge_library_service import KnowledgeLibraryService

    source = inspect.getsource(KnowledgeLibraryService.extract_principle_batches)
    assert "can_spend" in source, (
        "el bucle de lotes es la unico llamada que puede encadenar ~40 "
        "llamadas por documento y no comprobaba presupuesto"
    )
    assert "budget.record" in source, (
        "las llamadas de este bucle no se contabilizaban en budget_usage, asi "
        "que el gasto real no se compedia contra el tope"
    )


def test_estimate_cost_eur_scales_with_input_size():
    from app.services.budget import BudgetController

    cheap = BudgetController.estimate_cost_eur("x", 100, 100)
    pricey = BudgetController.estimate_cost_eur("x", 100_000, 100)
    assert pricey > cheap * 10
