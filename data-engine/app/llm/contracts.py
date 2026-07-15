from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    role: MessageRole | str
    content: str

    def __post_init__(self) -> None:
        try:
            role = self.role if isinstance(self.role, MessageRole) else MessageRole(self.role)
        except ValueError as exc:
            raise ValueError(f"Unsupported message role: {self.role!r}") from exc
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("Message content must be a non-empty string")
        object.__setattr__(self, "role", role)


@dataclass(frozen=True, slots=True)
class ResponseFormat:
    type: str = "json_object"
    schema: Mapping[str, Any] | None = None
    name: str = "response"
    strict: bool = True

    def __post_init__(self) -> None:
        if self.type not in {"json_object", "json_schema"}:
            raise ValueError("Response format type must be 'json_object' or 'json_schema'")
        if self.type == "json_schema" and self.schema is None:
            raise ValueError("A schema is required for json_schema responses")

    @classmethod
    def json_object(cls) -> ResponseFormat:
        return cls(type="json_object")

    @classmethod
    def json_schema(
        cls,
        schema: Mapping[str, Any],
        *,
        name: str = "response",
        strict: bool = True,
    ) -> ResponseFormat:
        return cls(type="json_schema", schema=schema, name=name, strict=strict)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: Sequence[Message]
    task: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: ResponseFormat | None = None
    materiality_score: int = 0
    portfolio_weight: float = 0.0
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        messages = tuple(self.messages)
        if not messages:
            raise ValueError("At least one message is required")
        if any(not isinstance(message, Message) for message in messages):
            raise TypeError("All messages must be Message instances")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive")
        if not 0 <= self.materiality_score <= 10:
            raise ValueError("materiality_score must be between 0 and 10")
        if not 0 <= self.portfolio_weight <= 1:
            raise ValueError("portfolio_weight must be between 0 and 1")
        object.__setattr__(self, "messages", messages)


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __post_init__(self) -> None:
        if min(
            self.input_tokens,
            self.output_tokens,
            self.total_tokens,
            self.cache_read_tokens,
            self.cache_write_tokens,
        ) < 0:
            raise ValueError("Token usage cannot be negative")


@dataclass(frozen=True, slots=True)
class LLMResponse:
    message: Message
    usage: Usage
    model: str
    provider: str
    finish_reason: str | None = None
    request_id: str | None = None

    @property
    def text(self) -> str:
        return self.message.content


LLMMessage = Message
LLMUsage = Usage
