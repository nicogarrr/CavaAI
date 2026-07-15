from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    reason: str
    max_materiality: int | None = None


ROUTES = {
    "cheap_extraction": ModelRoute("cheap_extraction", "qwen-flash", "low-cost structured extraction"),
    "main_financial_analysis": ModelRoute("main_financial_analysis", "qwen3.7-plus", "source-grounded financial analysis"),
    "agentic_red_team": ModelRoute("agentic_red_team", "glm-5.2", "tool-using adversarial review"),
    "news_triage": ModelRoute("news_triage", "qwen-flash", "cheap high-volume triage"),
    "dedupe_news": ModelRoute("dedupe_news", "qwen-flash", "cheap semantic dedupe"),
    "claim_extraction": ModelRoute("claim_extraction", "qwen-flash", "structured extraction"),
    "kpi_extraction": ModelRoute("kpi_extraction", "qwen-flash", "company-specific KPI extraction"),
    "pdf_summary": ModelRoute("pdf_summary", "qwen-flash", "long-context extraction summary"),
    "chat": ModelRoute("chat", "qwen3.7-plus", "grounded portfolio chat"),
    "thesis_update": ModelRoute("thesis_update", "qwen3.7-plus", "partial thesis update"),
    "deep_thesis": ModelRoute("deep_thesis", "glm-5.2", "deep thesis workflow"),
    "red_team": ModelRoute("red_team", "glm-5.2", "agentic red team"),
    "source_audit": ModelRoute("source_audit", "glm-5.2", "critical source audit"),
    "tool_workflow": ModelRoute("tool_workflow", "glm-5.2", "complex tool calling"),
    "code": ModelRoute("code", "kimi-k2.7-code", "product coding"),
    "premium_financial_analysis": ModelRoute("premium_financial_analysis", "qwen3.7-max", "eval-gated premium escalation"),
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
