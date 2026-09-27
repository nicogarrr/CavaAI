from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.llm.factory import create_llm_provider
from app.services.budget import BudgetController
from app.services.llm_router import route_table

router = APIRouter()


def maf_version() -> str:
    """Versión MAF real desde metadata del paquete (nunca hardcodeada)."""
    try:
        return f"agent-framework-core=={_pkg_version('agent-framework-core')}"
    except PackageNotFoundError:
        return "agent-framework-core==unknown"


@router.get("")
def settings(db: Session = Depends(get_db)) -> dict:
    app_settings = get_settings()
    provider = create_llm_provider(app_settings)
    llm_status: dict = {
        "provider": provider.name,
        "configured": provider.name != "disabled",
        # Model only when active; the API key is never exposed here.
        "model": app_settings.opencode_go_model if provider.name != "disabled" else None,
    }
    if provider.name == "disabled":
        llm_status["reason"] = getattr(provider, "reason", "disabled")
    return {
        "app_env": app_settings.app_env,
        "maf_version": maf_version(),
        # Vista de operacion: con sesion autenticada muestra el consumo del
        # tenant; sin contexto (sesion anonima), el agregado global es el
        # contexto admin y se pide explicitamente.
        "budget": BudgetController().current_usage(
            db, admin=db.info.get("tenant_id") is None
        ),
        "routes": route_table(),
        "llm": llm_status,
        "connectors": {
            "fmp": bool(app_settings.fmp_api_key),
            "ibkr": bool(app_settings.ibkr_flex_token and app_settings.ibkr_flex_query_id),
            "fred": bool(app_settings.fred_api_key),
            "manual_transcript_import": "available",
            "langfuse": app_settings.langfuse_enabled,
            # Booleano de presencia: la URL (posible secreto de red) jamás
            # sale por la API.
            "qdrant_url": bool(app_settings.qdrant_url),
        },
    }
