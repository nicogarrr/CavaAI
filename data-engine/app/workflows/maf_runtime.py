from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Never

from agent_framework import FunctionExecutor, WorkflowBuilder, WorkflowContext


MAF_WORKFLOWS = {
    "DeepResearchWorkflow",
    "EarningsWorkflow",
    "ThesisReviewWorkflow",
    "RedTeamWorkflow",
}


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class DeterministicWorkflowRunner:
    """Runner for ingestion, SQL, metrics, valuation and other deterministic work."""

    def __init__(self, name: str, steps: list[WorkflowStep]) -> None:
        self.name = name
        self.steps = steps

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = {"workflow": self.name, "execution_mode": "deterministic", "input": payload, "events": []}
        for step in self.steps:
            result = step.handler({**state, **payload})
            state["events"].append({"step": step.name, "result": result})
            state.update(result)
        return state


@dataclass(frozen=True)
class NativeMAFStep:
    name: str
    handler: Callable[
        [dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]
    ]


class NativeMAFWorkflowRunner:
    """Microsoft Agent Framework graph restricted to genuinely agentic reviews."""

    def __init__(self, name: str, steps: list[NativeMAFStep]) -> None:
        if name not in MAF_WORKFLOWS:
            raise ValueError(
                f"{name} is deterministic product infrastructure and may not run through MAF"
            )
        if not steps:
            raise ValueError("A MAF workflow requires at least one step")
        self.name = name
        self.steps = steps
        self.workflow = self._build()

    def _build(self):
        executors = []
        for index, step in enumerate(self.steps):
            is_last = index == len(self.steps) - 1

            def make_execute(current_step: NativeMAFStep, last: bool):
                async def execute(
                    message: dict[str, Any],
                    ctx: WorkflowContext[dict[str, Any], dict[str, Any]],
                ) -> None:
                    result = current_step.handler(message)
                    if inspect.isawaitable(result):
                        result = await result
                    state = {
                        **message,
                        **result,
                        "workflow": self.name,
                        "execution_mode": "microsoft_agent_framework",
                        "events": [
                            *(message.get("events") or []),
                            {"step": current_step.name, "result": result},
                        ],
                    }
                    if last:
                        await ctx.yield_output(state)
                    else:
                        await ctx.send_message(state)

                return execute

            execute = make_execute(step, is_last)

            executors.append(
                FunctionExecutor(
                    execute,
                    id=step.name,
                    input=dict,
                    output=dict if not is_last else Never,
                    workflow_output=dict if is_last else Never,
                )
            )
        builder = WorkflowBuilder(
            name=self.name,
            start_executor=executors[0],
            output_from=[executors[-1]],
        )
        if len(executors) > 1:
            builder.add_chain(executors)
        return builder.build()

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.workflow.run(payload)
        outputs = result.get_outputs()
        if not outputs:
            raise RuntimeError(f"{self.name} completed without a workflow output")
        return outputs[-1]


def maf_available() -> bool:
    try:
        import agent_framework  # noqa: F401

        return True
    except Exception:
        return False
