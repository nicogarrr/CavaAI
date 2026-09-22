from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
from app.services.workflow_run_service import WorkflowEnvelope, begin_run
from app.workflows.catalog import WORKFLOW_CATALOG

router = APIRouter()


class WorkflowRunRequest(BaseModel):
    ticker: str | None = None
    params: dict = Field(default_factory=dict)


@router.get("")
def workflows() -> dict:
    return {"workflows": WORKFLOW_CATALOG}


@router.get("/{name}")
def get_workflow(name: str) -> dict:
    workflow = next((w for w in WORKFLOW_CATALOG if w["name"] == name), None)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return workflow


def _replay_response(envelope: WorkflowEnvelope, workflow: dict, ticker: str | None) -> dict:
    """Stored result for an idempotent re-delivery; the work does not run twice."""
    stored = dict(envelope.run.result_payload or {})
    return {
        **stored,
        "run_id": envelope.run.id,
        "idempotent_replay": True,
        "steps": workflow["steps"],
        "estimated_minutes": 0,
        "workflow": workflow["name"],
        "ticker": ticker,
    }


@router.post("/{name}/run")
async def run_workflow(
    name: str,
    payload: WorkflowRunRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None),
) -> dict:
    workflow = next((w for w in WORKFLOW_CATALOG if w["name"] == name), None)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

    key = idempotency_key or payload.params.get("idempotency_key")

    def open_envelope(input_payload: dict) -> WorkflowEnvelope:
        return begin_run(
            db,
            name,
            execution_mode=workflow.get("execution_mode"),
            input_payload=input_payload,
            idempotency_key=key,
        )

    if name == "GenerateThesisWorkflow" and payload.ticker:
        ticker = payload.ticker.upper()
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        envelope = open_envelope({"ticker": ticker, "params": payload.params})
        if envelope.replayed:
            return _replay_response(envelope, workflow, ticker)
        try:
            from app.services.thesis_service import ThesisService

            def generate() -> dict:
                thesis = ThesisService().generate(db, ticker, force_new_version=True)
                return {
                    "thesis_id": thesis.id,
                    "version": thesis.version,
                    "status": thesis.status,
                    "rating": thesis.rating,
                }

            # Un solo paso ejecutado: la generacion es una transaccion sincrona.
            result = envelope.record_step(1, "generate_thesis", generate)
            envelope.finish({"status": "completed", "result": result})
            return {
                "status": "completed",
                "workflow": name,
                "ticker": ticker,
                "run_id": envelope.run.id,
                "result": result,
                "steps": workflow["steps"],
                "estimated_minutes": 0,
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if name == "DailyResearchWorkflow" and payload.params.get("news_items"):
        from app.schemas import NewsFeedItem
        from app.services.news_service import NewsService

        envelope = open_envelope({"ticker": payload.ticker, "params": payload.params})
        if envelope.replayed:
            return _replay_response(envelope, workflow, payload.ticker)
        items = [NewsFeedItem.model_validate(item) for item in payload.params["news_items"]]

        def ingest() -> dict:
            result = NewsService().ingest_news_items(
                db,
                items,
                payload.params.get("source", "daily_research_feed"),
            )
            return result.model_dump(mode="json")

        result = envelope.record_step(1, "ingest_news_items", ingest)
        envelope.finish({"status": "completed", "result": result})
        return {
            "status": "completed",
            "workflow": name,
            "ticker": payload.ticker,
            "run_id": envelope.run.id,
            "message": "Daily research news ingestion completed.",
            "steps": workflow["steps"],
            "estimated_minutes": 0,
            "result": result,
        }

    if name == "EarningsWorkflow" and payload.ticker:
        from datetime import datetime

        from app.services.earnings_service import EarningsWorkflowService
        from app.workflows.maf_runtime import NativeMAFStep, NativeMAFWorkflowRunner

        ticker = payload.ticker.upper()
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        def load_context(state: dict) -> dict:
            return {
                "ticker": ticker,
                "fiscal_year": int(payload.params.get("fiscal_year", datetime.now().year)),
                "fiscal_quarter": str(payload.params.get("fiscal_quarter", "FY")),
                "document_ids": [int(item) for item in payload.params.get("document_ids", [])],
            }

        def execute_review(state: dict) -> dict:
            run = EarningsWorkflowService().run(
                db,
                company,
                fiscal_year=state["fiscal_year"],
                fiscal_quarter=state["fiscal_quarter"],
                document_ids=state["document_ids"],
                force_new_thesis=bool(payload.params.get("force_new_thesis", False)),
            )
            return {
                "run": {
                    "status": run.status,
                    "error": run.error,
                    "earnings_run_id": run.id,
                    "thesis_change_id": run.thesis_change_id,
                    "documents": run.document_ids,
                    "metrics": len(run.extracted_metrics),
                    "guidance_changes": len(run.guidance_changes),
                }
            }

        envelope = open_envelope({"ticker": ticker, "params": payload.params})
        if envelope.replayed:
            return _replay_response(envelope, workflow, ticker)
        maf_result = await NativeMAFWorkflowRunner(
            "EarningsWorkflow",
            [
                NativeMAFStep("load_earnings_context", load_context),
                NativeMAFStep("execute_earnings_review", execute_review),
            ],
            recorder=envelope.record_step,
        ).run({"ticker": ticker})
        run = maf_result["run"]
        result = {
            "earnings_run_id": run["earnings_run_id"],
            "thesis_change_id": run["thesis_change_id"],
            "documents": run["documents"],
            "metrics": run["metrics"],
            "guidance_changes": run["guidance_changes"],
        }
        if run["status"] == "completed":
            envelope.finish({"status": "completed", "result": result})
        else:
            envelope.run.status = "failed"
            envelope.run.error_message = (run["error"] or "Earnings workflow failed")[:1000]
            from app.services.workflow_run_service import _safe_commit

            _safe_commit(db, "earnings run failed")
        return {
            "status": run["status"],
            "workflow": name,
            "execution_mode": maf_result["execution_mode"],
            "ticker": ticker,
            "run_id": envelope.run.id,
            "message": run["error"] or "Earnings workflow completed.",
            "steps": workflow["steps"],
            "estimated_minutes": 0,
            "result": result,
        }

    if name == "RedTeamWorkflow" and payload.ticker:
        from app.services.red_team_service import RedTeamService
        from app.workflows.maf_runtime import NativeMAFStep, NativeMAFWorkflowRunner

        ticker = payload.ticker.upper()
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        def load_evidence(state: dict) -> dict:
            return {"ticker": ticker, "review_scope": "thesis_evidence_and_assumptions"}

        def execute_red_team(state: dict) -> dict:
            run = RedTeamService().run(db, company)
            return {
                "run": {
                    "status": run.status,
                    "red_team_run_id": run.id,
                    "score": run.score,
                    "findings": len(run.findings),
                }
            }

        envelope = open_envelope({"ticker": ticker, "params": payload.params})
        if envelope.replayed:
            return _replay_response(envelope, workflow, ticker)
        maf_result = await NativeMAFWorkflowRunner(
            "RedTeamWorkflow",
            [
                NativeMAFStep("load_review_evidence", load_evidence),
                NativeMAFStep("execute_adversarial_review", execute_red_team),
            ],
            recorder=envelope.record_step,
        ).run({"ticker": ticker})
        run = maf_result["run"]
        result = {
            "red_team_run_id": run["red_team_run_id"],
            "score": run["score"],
            "findings": run["findings"],
        }
        envelope.finish({"status": "completed", "result": result})
        return {
            "status": run["status"],
            "workflow": name,
            "execution_mode": maf_result["execution_mode"],
            "ticker": ticker,
            "run_id": envelope.run.id,
            "message": "Red-team workflow completed.",
            "steps": workflow["steps"],
            "estimated_minutes": 0,
            "result": result,
        }

    # Verdad por encima de apariencia: ningun worker generico consume una
    # peticion "queued". Si no hay ruta de ejecucion, se dice claro.
    return {
        "status": "not_implemented",
        "workflow": name,
        "ticker": payload.ticker,
        "message": (
            f"Workflow {name} no tiene ejecucion via API: es una entrada "
            f"{workflow.get('implementation_status', 'descriptive')} del catalogo. "
            "Los trabajos periodicos equivalentes corren via scheduler/Dramatiq."
        ),
        "steps": workflow["steps"],
        "estimated_minutes": 0,
    }
