from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRoute:
    task: str
    model: str
    reason: str
    max_materiality: int | None = None


ROUTES = {
    "cheap_extraction": ModelRoute("cheap_extraction", "space-bunny-free", "low-cost structured extraction"),
    "main_financial_analysis": ModelRoute("main_financial_analysis", "space-bunny-free", "source-grounded financial analysis"),
    "agentic_red_team": ModelRoute("agentic_red_team", "space-bunny-free", "tool-using adversarial review"),
    "news_triage": ModelRoute("news_triage", "space-bunny-free", "cheap high-volume triage"),
    "dedupe_news": ModelRoute("dedupe_news", "space-bunny-free", "cheap semantic dedupe"),
    "claim_extraction": ModelRoute("claim_extraction", "space-bunny-free", "structured extraction"),
    "kpi_extraction": ModelRoute("kpi_extraction", "space-bunny-free", "company-specific KPI extraction"),
    "pdf_summary": ModelRoute("pdf_summary", "space-bunny-free", "long-context extraction summary"),
    "chat": ModelRoute("chat", "space-bunny-free", "grounded portfolio chat"),
    "thesis_update": ModelRoute("thesis_update", "space-bunny-free", "partial thesis update"),
    "deep_thesis": ModelRoute("deep_thesis", "space-bunny-free", "deep thesis workflow"),
    "red_team": ModelRoute("red_team", "space-bunny-free", "agentic red team"),
    "source_audit": ModelRoute("source_audit", "space-bunny-free", "critical source audit"),
    "tool_workflow": ModelRoute("tool_workflow", "space-bunny-free", "complex tool calling"),
    "code": ModelRoute("code", "space-bunny-free", "product coding"),
    "premium_financial_analysis": ModelRoute("premium_financial_analysis", "space-bunny-free", "eval-gated premium escalation"),
    "fallback": ModelRoute("fallback", "space-bunny-free", "cheap fallback"),
}


def route_model(task: str, materiality_score: int = 0, portfolio_weight: float = 0) -> ModelRoute:
    if task == "deep_thesis" and materiality_score < 7 and portfolio_weight < 0.05:
        return ROUTES["thesis_update"]
    if task == "red_team" and materiality_score < 8 and portfolio_weight < 0.08:
        return ROUTES["thesis_update"]
    return ROUTES.get(task, ROUTES["fallback"])


def route_table() -> list[dict]:
    from app.llm.model_aliases import MODEL_ALIASES

    rows = []
    for route in ROUTES.values():
        alias = MODEL_ALIASES.get(route.model)
        rows.append(
            {
                **route.__dict__,
                "provider": alias.provider if alias else None,
                "provider_model_id": alias.provider_model_id if alias else None,
                "enabled": alias.enabled if alias else False,
                "context_window": alias.context_window if alias else None,
                "input_cost": str(alias.input_cost) if alias else None,
                "output_cost": str(alias.output_cost) if alias else None,
                "supported_capabilities": sorted(alias.supported_capabilities) if alias else [],
            }
        )
    return rows
