from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    reason: str
    max_materiality: int | None = None


ROUTES = {
    "news_triage": ModelRoute("news_triage", "mimo-v2.5", "cheap high-volume triage"),
    "dedupe_news": ModelRoute("dedupe_news", "mimo-v2.5", "cheap semantic dedupe"),
    "claim_extraction": ModelRoute("claim_extraction", "mimo-v2.5", "structured extraction"),
    "pdf_summary": ModelRoute("pdf_summary", "mimo-v2.5", "long-context summary"),
    "chat": ModelRoute("chat", "mimo-v2.5-pro", "normal grounded portfolio chat"),
    "thesis_update": ModelRoute("thesis_update", "mimo-v2.5-pro", "partial thesis update"),
    "deep_thesis": ModelRoute("deep_thesis", "qwen3.7-max", "deep thesis and red team"),
    "red_team": ModelRoute("red_team", "qwen3.7-max", "important red team"),
    "source_audit": ModelRoute("source_audit", "glm-5.2", "critical source audit"),
    "tool_workflow": ModelRoute("tool_workflow", "glm-5.2", "complex tool calling"),
    "code": ModelRoute("code", "kimi-k2.7-code", "product coding"),
    "fallback": ModelRoute("fallback", "deepseek-v4-flash", "cheap fallback"),
}


def route_model(task: str, materiality_score: int = 0, portfolio_weight: float = 0) -> ModelRoute:
    if task == "deep_thesis" and materiality_score < 7 and portfolio_weight < 0.05:
        return ROUTES["thesis_update"]
    if task == "red_team" and materiality_score < 8 and portfolio_weight < 0.08:
        return ROUTES["thesis_update"]
    return ROUTES.get(task, ROUTES["fallback"])


def route_table() -> list[dict]:
    return [route.__dict__ for route in ROUTES.values()]

