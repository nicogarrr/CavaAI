from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from app.llm.contracts import LLMRequest
from app.llm.model_aliases import MODEL_ALIASES


@dataclass(frozen=True, slots=True)
class TaskModelRouter:
    """Resolve models while retaining the application's existing task policy."""

    default_model: str
    overrides: Mapping[str, str] = field(default_factory=dict)
    provider: str | None = None

    def resolve(self, request: LLMRequest) -> str:
        if request.model:
            model = request.model
        elif request.task is None:
            model = self.default_model
        elif request.task in self.overrides:
            model = self.overrides[request.task]
        else:
            # Import lazily so the provider layer does not make the legacy router
            # import-time state and so callers can continue testing its policy.
            from app.services.llm_router import route_model

            route = route_model(
                request.task,
                materiality_score=request.materiality_score,
                portfolio_weight=request.portfolio_weight,
            )
            model = self.overrides.get(
                route.task,
                self.overrides.get(route.model, route.model),
            )
        return MODEL_ALIASES.resolve(model, provider=self.provider) if self.provider else model
