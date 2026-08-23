from fastapi import APIRouter

from app.api.routes import (
    alerts,
    chat,
    companies,
    corporate_actions,
    earnings,
    export,
    knowledge,
    knowledge_graph,
    market,
    memory,
    news,
    plan,
    portfolio,
    risk,
    reviews,
    search,
    screeners,
    settings,
    sources,
    taxes,
    thesis,
    valuation,
    watchlist,
    work_products,
    workflows,
)

api_router = APIRouter()
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(companies.router, prefix="/companies", tags=["companies"])
api_router.include_router(
    corporate_actions.router, prefix="/corporate-actions", tags=["corporate-actions"]
)
api_router.include_router(earnings.router, prefix="/earnings", tags=["earnings"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(plan.router, prefix="/plan", tags=["plan"])
api_router.include_router(taxes.router, prefix="/taxes", tags=["taxes"])
api_router.include_router(thesis.router, prefix="/thesis", tags=["thesis"])
api_router.include_router(valuation.router, prefix="/valuation", tags=["valuation"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(
    work_products.router, prefix="/work-products", tags=["work-products"]
)
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
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
