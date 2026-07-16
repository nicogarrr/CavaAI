from fastapi import APIRouter

from app.api.routes import (
    alerts,
    chat,
    companies,
    earnings,
    knowledge,
    knowledge_graph,
    memory,
    news,
    portfolio,
    risk,
    reviews,
    search,
    screeners,
    settings,
    sources,
    thesis,
    valuation,
    workflows,
)

api_router = APIRouter()
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(earnings.router, prefix="/earnings", tags=["earnings"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(thesis.router, prefix="/thesis", tags=["thesis"])
api_router.include_router(valuation.router, prefix="/valuation", tags=["valuation"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(
    knowledge_graph.router, prefix="/knowledge-graph", tags=["knowledge-graph"]
)
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(screeners.router, prefix="/screeners", tags=["screeners"])
api_router.include_router(memory.router, prefix="/memory", tags=["memory"])
api_router.include_router(sources.router, prefix="/sources", tags=["sources"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
