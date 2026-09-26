"""Tests de `app.workflows.maf_runtime` (runner determinista + grafo MAF nativo).

Sin BD, sin red: los handlers son funciones puras; el grafo nativo de Microsoft
Agent Framework se ejecuta en proceso (sin LLM ni llamadas externas).
"""

from __future__ import annotations

import asyncio

import pytest

from app.workflows.maf_runtime import (
    MAF_WORKFLOWS,
    DeterministicWorkflowRunner,
    NativeMAFStep,
    NativeMAFWorkflowRunner,
    WorkflowStep,
    maf_available,
)


def _step_a(state: dict) -> dict:
    return {"a": state.get("x", 0) + 1}


def _step_b(state: dict) -> dict:
    return {"b": state["a"] * 2}


# ---------------- DeterministicWorkflowRunner ----------------


def test_runner_determinista_encadena_pasos_y_acumula_estado():
    runner = DeterministicWorkflowRunner(
        "demo", [WorkflowStep("a", _step_a), WorkflowStep("b", _step_b)]
    )
    result = runner.run({"x": 1})

    assert result["workflow"] == "demo"
    assert result["execution_mode"] == "deterministic"
    assert result["input"] == {"x": 1}
    assert result["a"] == 2
    assert result["b"] == 4
    assert result["events"] == [
        {"step": "a", "result": {"a": 2}},
        {"step": "b", "result": {"b": 4}},
    ]


def test_runner_determinista_sin_pasos_devuelve_estado_vacio_de_eventos():
    runner = DeterministicWorkflowRunner("vacio", [])
    result = runner.run({"x": 1})
    assert result["events"] == []
    assert result["input"] == {"x": 1}


def test_recorder_recibe_posicion_nombre_y_thunk():
    calls: list[tuple[int, str]] = []
    results: list[dict] = []

    def recorder(position: int, name: str, thunk):
        calls.append((position, name))
        outcome = thunk()
        results.append(outcome)
        return outcome

    runner = DeterministicWorkflowRunner(
        "demo", [WorkflowStep("a", _step_a), WorkflowStep("b", _step_b)], recorder=recorder
    )
    result = runner.run({"x": 5})

    assert calls == [(1, "a"), (2, "b")]
    assert results == [{"a": 6}, {"b": 12}]
    assert result["b"] == 12


def test_recorder_puede_transformar_el_resultado():
    """El recorder es el unico que invoca el handler: puede sellar la salida."""

    def recorder(position, name, thunk):
        return {"sello": name, **thunk()}

    runner = DeterministicWorkflowRunner(
        "demo", [WorkflowStep("a", _step_a)], recorder=recorder
    )
    result = runner.run({"x": 1})
    assert result["sello"] == "a"
    assert result["a"] == 2


def test_payload_sobreescribe_al_estado_en_los_handlers():
    """Los handlers ven {**state, **payload}: el payload manda (contrato documentado)."""

    def spy(state: dict) -> dict:
        return {"visto": state["x"]}

    runner = DeterministicWorkflowRunner("demo", [WorkflowStep("s", spy)])
    assert runner.run({"x": "payload"})["visto"] == "payload"


def test_estado_de_pasos_previos_es_visible_en_los_siguientes():
    visto = {}

    def segundo(state: dict) -> dict:
        visto["a_previo"] = state.get("a")
        return {}

    runner = DeterministicWorkflowRunner(
        "demo", [WorkflowStep("a", _step_a), WorkflowStep("b", segundo)]
    )
    runner.run({"x": 1})
    assert visto["a_previo"] == 2


# ---------------- NativeMAFWorkflowRunner ----------------


def test_solo_se_permiten_workflows_agenticos_declarados():
    assert {
        "DeepResearchWorkflow",
        "EarningsWorkflow",
        "ThesisReviewWorkflow",
        "RedTeamWorkflow",
    } == MAF_WORKFLOWS
    with pytest.raises(ValueError, match="may not run through MAF"):
        NativeMAFWorkflowRunner("ScreenerWorkflow", [NativeMAFStep("a", _step_a)])
    with pytest.raises(ValueError, match="may not run through MAF"):
        NativeMAFWorkflowRunner("ValuationWorkflow", [NativeMAFStep("a", _step_a)])


def test_workflow_nativo_requiere_al_menos_un_paso():
    with pytest.raises(ValueError, match="at least one step"):
        NativeMAFWorkflowRunner("RedTeamWorkflow", [])


def test_maf_available_devuelve_bool():
    assert isinstance(maf_available(), bool)


@pytest.mark.skipif(not maf_available(), reason="agent_framework no instalado")
def test_workflow_nativo_ejecuta_cadena_con_handlers_sync_y_async():
    async def async_step(state: dict) -> dict:
        return {"async_marker": state.get("x", 0) * 10}

    runner = NativeMAFWorkflowRunner(
        "RedTeamWorkflow", [NativeMAFStep("a", _step_a), NativeMAFStep("b", async_step)]
    )
    result = asyncio.run(runner.run({"x": 3}))

    assert result["a"] == 4
    assert result["async_marker"] == 30
    assert result["workflow"] == "RedTeamWorkflow"
    assert result["execution_mode"] == "microsoft_agent_framework"
    assert [event["step"] for event in result["events"]] == ["a", "b"]


@pytest.mark.skipif(not maf_available(), reason="agent_framework no instalado")
def test_workflow_nativo_de_un_solo_paso_tambien_publica_salida():
    runner = NativeMAFWorkflowRunner("EarningsWorkflow", [NativeMAFStep("solo", _step_a)])
    result = asyncio.run(runner.run({"x": 10}))
    assert result["a"] == 11
    assert len(result["events"]) == 1


@pytest.mark.skipif(not maf_available(), reason="agent_framework no instalado")
def test_workflow_nativo_con_recorder_registra_cada_paso():
    calls: list[tuple[int, str]] = []

    def recorder(position, name, thunk):
        calls.append((position, name))
        return thunk()

    runner = NativeMAFWorkflowRunner(
        "ThesisReviewWorkflow",
        [NativeMAFStep("a", _step_a), NativeMAFStep("b", _step_b)],
        recorder=recorder,
    )
    result = asyncio.run(runner.run({"x": 1}))
    assert calls == [(1, "a"), (2, "b")]
    assert result["b"] == 4


@pytest.mark.skipif(not maf_available(), reason="agent_framework no instalado")
def test_handler_async_sin_resultado_es_awaitado_por_el_runner():
    async def devuelvo_none(_state: dict) -> dict:
        await asyncio.sleep(0)
        return {"ok": True}

    runner = NativeMAFWorkflowRunner(
        "DeepResearchWorkflow",
        [NativeMAFStep("paso", devuelvo_none)],
    )
    assert asyncio.run(runner.run({}))["ok"] is True
