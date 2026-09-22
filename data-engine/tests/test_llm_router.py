"""LLM routing contracts: cost/quality downgrade boundaries.

route_model decides when an expensive workflow is downgraded to the cheap
thesis-update route. The boundaries are product-visible (analysis depth vs
cost), so they must be pinned exactly.
"""

from app.services.llm_router import ROUTES, route_model, route_table


def test_deep_thesis_downgrades_only_when_both_below_threshold():
    route = route_model("deep_thesis", materiality_score=6, portfolio_weight=0.04)
    assert route.task == "thesis_update"


def test_deep_thesis_holds_when_either_signal_is_strong():
    assert route_model("deep_thesis", materiality_score=6, portfolio_weight=0.10).task == "deep_thesis"
    assert route_model("deep_thesis", materiality_score=9, portfolio_weight=0.04).task == "deep_thesis"


def test_deep_thesis_holds_at_boundaries():
    route = route_model("deep_thesis", materiality_score=7, portfolio_weight=0.05)
    assert route.task == "deep_thesis"


def test_red_team_downgrades_only_when_both_below_threshold():
    assert route_model("red_team", materiality_score=7, portfolio_weight=0.07).task == "thesis_update"
    assert route_model("red_team", materiality_score=7, portfolio_weight=0.10).task == "red_team"
    assert route_model("red_team", materiality_score=9, portfolio_weight=0.07).task == "red_team"
    assert route_model("red_team", materiality_score=8, portfolio_weight=0.08).task == "red_team"


def test_unknown_task_falls_back_explicitly():
    route = route_model("nonexistent_task")
    assert route is ROUTES["fallback"]


def test_route_table_marks_unconfigured_models_disabled():
    rows = {row["task"]: row for row in route_table()}
    assert set(rows) == set(ROUTES)
    for row in rows.values():
        assert isinstance(row["enabled"], bool)
        # Every route must resolve an alias or be honestly disabled - never
        # silently claim a provider it does not have.
        if row["provider"] is None:
            assert row["enabled"] is False
