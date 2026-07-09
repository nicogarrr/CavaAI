from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Company
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


@router.post("/{name}/run")
async def run_workflow(name: str, payload: WorkflowRunRequest, db: Session = Depends(get_db)) -> dict:
    workflow = next((w for w in WORKFLOW_CATALOG if w["name"] == name), None)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")

    if name == "GenerateThesisWorkflow" and payload.ticker:
        ticker = payload.ticker.upper()
        company = db.scalar(select(Company).where(Company.ticker == ticker))
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {ticker} not found")
        try:
            from app.services.thesis_service import ThesisService
            thesis = ThesisService().generate(db, ticker, force_new_version=True)
            return {
                "status": "completed",
                "workflow": name,
                "ticker": ticker,
                "result": {
                    "thesis_id": thesis.id,
                    "version": thesis.version,
                    "status": thesis.status,
                    "rating": thesis.rating,
                },
                "steps": workflow["steps"],
                "estimated_minutes": 0,
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if name == "DailyResearchWorkflow" and payload.params.get("news_items"):
        from app.schemas import NewsFeedItem
        from app.services.news_service import NewsService

        items = [NewsFeedItem.model_validate(item) for item in payload.params["news_items"]]
        result = NewsService().ingest_news_items(
            db,
            items,
            payload.params.get("source", "daily_research_feed"),
        )
        return {
            "status": "completed",
            "workflow": name,
            "ticker": payload.ticker,
            "message": "Daily research news ingestion completed.",
            "steps": workflow["steps"],
            "estimated_minutes": 0,
            "result": result.model_dump(mode="json"),
        }

    return {
        "status": "queued",
        "workflow": name,
        "ticker": payload.ticker,
        "message": f"Workflow {name} queued. Backend worker required to execute.",
        "steps": workflow["steps"],
        "estimated_minutes": len(workflow["steps"]) * 2,
    }
