from sqlalchemy.orm import Session

from app.services.thesis_service import ThesisService
from app.workflows.maf_runtime import LocalWorkflowRunner, WorkflowStep


def build_generate_thesis_workflow(db: Session) -> LocalWorkflowRunner:
    service = ThesisService()

    def generate(state: dict) -> dict:
        thesis = service.generate(db, state["ticker"], force_new_version=state.get("force", False))
        return {"thesis_id": thesis.id, "version": thesis.version, "status": thesis.status}

    return LocalWorkflowRunner(
        "GenerateThesisWorkflow",
        [
            WorkflowStep("resolve_ticker", lambda state: {"ticker": state["ticker"].upper()}),
            WorkflowStep("run_python_valuation", lambda state: {"calculation_required": True}),
            WorkflowStep("source_audit_and_save", generate),
        ],
    )

