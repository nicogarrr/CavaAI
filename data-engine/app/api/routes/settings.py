from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.services.budget import BudgetController
from app.services.llm_router import route_table

router = APIRouter()


@router.get("")
def settings(db: Session = Depends(get_db)) -> dict:
    app_settings = get_settings()
    return {
        "app_env": app_settings.app_env,
        "maf_version": "agent-framework-core==1.10.0",
        "budget": BudgetController().current_usage(db),
        "routes": route_table(),
        "connectors": {
            "fmp": bool(app_settings.fmp_api_key),
            "ibkr": bool(app_settings.ibkr_flex_token and app_settings.ibkr_flex_query_id),
            "fred": bool(app_settings.fred_api_key),
            "manual_transcript_import": "available",
            "langfuse": app_settings.langfuse_enabled,
            "qdrant_url": app_settings.qdrant_url,
        },
    }
