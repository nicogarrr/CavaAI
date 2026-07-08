"""FastAPI bootstrap for the CavaAI data engine."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router as research_api_router
from app.core.database import init_db
from routers.analytics import router as analytics_router
from routers.fundamentals import router as fundamentals_router
from routers.knowledge import router as knowledge_router
from routers.market import router as market_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="FMP Data Engine", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fundamentals_router)
app.include_router(market_router)
app.include_router(knowledge_router)
app.include_router(analytics_router)
app.include_router(research_api_router, prefix="/api")


@app.get("/")
async def root():
    return {"status": "ok", "service": "FMP Data Engine"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
