from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.llm.contracts import LLMRequest


@dataclass(frozen=True, slots=True)
class TaskModelRouter:
    """Resolve models while retaining the application's existing task policy."""

    default_model: str
    overrides: Mapping[str, str] = field(default_factory=dict)

    def resolve(self, request: LLMRequest) -> str:
        if request.model:
            return request.model
        if request.task is None:
            return self.default_model
        if request.task in self.overrides:
            return self.overrides[request.task]

        # Import lazily so the provider layer does not make the legacy router
        # import-time state and so callers can continue testing its policy.
        from app.services.llm_router import route_model

        route = route_model(
            request.task,
            materiality_score=request.materiality_score,
            portfolio_weight=request.portfolio_weight,
        )
        return self.overrides.get(
            route.task,
            self.overrides.get(route.model, route.model),
        )
