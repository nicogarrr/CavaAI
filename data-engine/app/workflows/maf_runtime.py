from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowStep:
    name: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class LocalWorkflowRunner:
    """Small deterministic fallback for local dev and tests.

    The project depends on `agent-framework==1.10.0`. This runner keeps the app
    usable when no model/provider credentials are configured; production
    workflow definitions can be swapped to native MAF graph executors.
    """

    def __init__(self, name: str, steps: list[WorkflowStep]) -> None:
        self.name = name
        self.steps = steps

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = {"workflow": self.name, "input": payload, "events": []}
        for step in self.steps:
            result = step.handler({**state, **payload})
            state["events"].append({"step": step.name, "result": result})
            state.update(result)
        return state


def maf_available() -> bool:
    try:
        import agent_framework  # noqa: F401

        return True
    except Exception:
        return False

