from fastapi import APIRouter

from app.api.routes import (
    chat,
    companies,
    news,
    portfolio,
    risk,
    settings,
    sources,
    thesis,
    valuation,
    workflows,
)

api_router = APIRouter()
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(thesis.router, prefix="/thesis", tags=["thesis"])
api_router.include_router(valuation.router, prefix="/valuation", tags=["valuation"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])

