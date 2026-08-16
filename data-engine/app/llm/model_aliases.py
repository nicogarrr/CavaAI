from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class ModelAlias:
    """Stable internal name mapped to a concrete provider model.

    Costs are current list prices in USD per million tokens.
    """

    internal_alias: str
    provider: str
    provider_model_id: str
    enabled: bool
    context_window: int
    input_cost: Decimal
    output_cost: Decimal
    supported_capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not self.internal_alias.strip():
            raise ValueError("ModelAlias.internal_alias cannot be empty")
        if not self.provider.strip():
            raise ValueError("ModelAlias.provider cannot be empty")
        if not self.provider_model_id.strip():
            raise ValueError("ModelAlias.provider_model_id cannot be empty")
        if self.context_window <= 0:
            raise ValueError("ModelAlias.context_window must be positive")
        if self.input_cost < 0 or self.output_cost < 0:
            raise ValueError("ModelAlias costs cannot be negative")
        if not self.supported_capabilities:
            raise ValueError("ModelAlias.supported_capabilities cannot be empty")


class _ModelRoute(Protocol):
    @property
    def task(self) -> str: ...

    @property
    def model(self) -> str: ...


OPENCODE_GO_MODEL_ALIASES = (
    ModelAlias(
        internal_alias="deepseek-v4-flash",
        provider="opencode-go",
        provider_model_id="deepseek-v4-flash",
        enabled=True,
        context_window=1_048_576,
        input_cost=Decimal("0"),
        output_cost=Decimal("0"),
        supported_capabilities=frozenset(
            {"text", "reasoning", "tool_calling", "structured_output"}
        ),
    ),
)


class ModelAliasRegistry:
    def __init__(self, aliases: Iterable[ModelAlias]) -> None:
        self.replace(aliases)

    def replace(self, aliases: Iterable[ModelAlias]) -> None:
        by_alias: dict[str, ModelAlias] = {}
        by_provider_id: dict[tuple[str, str], ModelAlias] = {}
        for alias in aliases:
            if alias.internal_alias in by_alias:
                raise ValueError(f"Duplicate model alias: {alias.internal_alias!r}")
            provider_key = (alias.provider, alias.provider_model_id)
            if provider_key in by_provider_id:
                raise ValueError(
                    f"Duplicate provider model id: {alias.provider}/{alias.provider_model_id}"
                )
            by_alias[alias.internal_alias] = alias
            by_provider_id[provider_key] = alias
        self._by_alias = MappingProxyType(by_alias)
        self._by_provider_id = MappingProxyType(by_provider_id)

    @property
    def aliases(self) -> Mapping[str, ModelAlias]:
        return self._by_alias

    def get(self, internal_alias: str) -> ModelAlias | None:
        return self._by_alias.get(internal_alias)

    def resolve(self, model: str, *, provider: str) -> str:
        alias = self._by_alias.get(model)
        if alias is None:
            registered_model = self._by_provider_id.get((provider, model))
            if registered_model is None:
                # Low-level adapters remain usable with explicit provider IDs.
                # Application task routes are checked strictly below.
                return model
            if not registered_model.enabled:
                raise ValueError(f"Provider model {model!r} is disabled")
            return model
        if not alias.enabled:
            raise ValueError(f"Model alias {model!r} is disabled")
        if alias.provider != provider:
            raise ValueError(
                f"Model alias {model!r} belongs to provider {alias.provider!r}, "
                f"not active provider {provider!r}"
            )
        return alias.provider_model_id

    def translated_overrides(
        self,
        *,
        provider: str,
        overrides: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        translated = {
            alias.internal_alias: alias.provider_model_id
            for alias in self._by_alias.values()
            if alias.provider == provider and alias.enabled
        }
        for key, model in (overrides or {}).items():
            translated[key] = self.resolve(model, provider=provider)
        return translated

    def validate_active_routes(
        self,
        routes: Iterable[_ModelRoute],
        *,
        provider: str,
        overrides: Mapping[str, str] | None = None,
    ) -> None:
        overrides = overrides or {}
        for route in routes:
            configured = overrides.get(route.task, overrides.get(route.model, route.model))
            registered = self._by_alias.get(configured) or self._by_provider_id.get(
                (provider, configured)
            )
            if registered is None:
                raise ValueError(
                    f"Active LLM task {route.task!r} references unknown model alias "
                    f"or provider model {configured!r}"
                )
            try:
                self.resolve(configured, provider=provider)
            except ValueError as exc:
                raise ValueError(
                    f"Active LLM task {route.task!r} references an unavailable model: {exc}"
                ) from exc


MODEL_ALIASES = ModelAliasRegistry(OPENCODE_GO_MODEL_ALIASES)


def configure_model_aliases(db) -> ModelAliasRegistry:
    """Load persisted aliases while preserving user enable/disable choices."""

    from sqlalchemy import select

    from app.models import ModelAlias as PersistedModelAlias

    existing = {
        (row.internal_alias, row.provider)
        for row in db.scalars(select(PersistedModelAlias)).all()
    }
    changed = False
    for alias in OPENCODE_GO_MODEL_ALIASES:
        if (alias.internal_alias, alias.provider) in existing:
            continue
        db.add(
            PersistedModelAlias(
                internal_alias=alias.internal_alias,
                provider=alias.provider,
                provider_model_id=alias.provider_model_id,
                enabled=alias.enabled,
                context_window=alias.context_window,
                input_cost=alias.input_cost,
                output_cost=alias.output_cost,
                supported_capabilities=sorted(alias.supported_capabilities),
            )
        )
        changed = True
    if changed:
        db.commit()

    rows = db.scalars(
        select(PersistedModelAlias).where(
            PersistedModelAlias.provider == "opencode-go"
        )
    ).all()
    MODEL_ALIASES.replace(
        ModelAlias(
            internal_alias=row.internal_alias,
            provider=row.provider,
            provider_model_id=row.provider_model_id,
            enabled=row.enabled,
            context_window=row.context_window,
            input_cost=Decimal(row.input_cost),
            output_cost=Decimal(row.output_cost),
            supported_capabilities=frozenset(row.supported_capabilities),
        )
        for row in rows
    )
    return MODEL_ALIASES
