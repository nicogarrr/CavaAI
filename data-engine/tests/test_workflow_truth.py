"""Stage 1 truth pass: the workflow catalog and run endpoint never overstate."""

from fastapi.testclient import TestClient

import main
from app.workflows.catalog import WORKFLOW_CATALOG


def test_every_catalog_entry_declares_implementation_status():
    statuses = {"implemented", "partial", "descriptive"}
    for workflow in WORKFLOW_CATALOG:
        assert workflow.get("implementation_status") in statuses, workflow["name"]
        assert workflow.get("truth"), workflow["name"]


def test_catalog_has_no_fake_langfuse_steps():
    for workflow in WORKFLOW_CATALOG:
        assert "trace_to_langfuse" not in workflow["steps"], workflow["name"]


def test_unknown_workflow_run_never_claims_queued():
    """Antes devolvia status=queued aunque ningun worker consumia la peticion."""
    client = TestClient(main.app)
    response = client.post("/api/workflows/DeepResearchWorkflow/run", json={"ticker": None, "params": {}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_implemented"
    assert "queued" not in payload["message"].lower()


def test_red_team_is_documented_as_deterministic():
    workflow = next(w for w in WORKFLOW_CATALOG if w["name"] == "RedTeamWorkflow")
    assert "DETERMINIST" in workflow["truth"].upper()
