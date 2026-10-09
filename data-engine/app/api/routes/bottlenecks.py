"""Persisted, tenant-scoped supply constraints. GET never ingests or calls AI."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import BottleneckSignal
from app.services.bottleneck_service import THEMES

router = APIRouter()


class BottleneckSignalOut(BaseModel):
    theme: str
    evidence_ids: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    n_sources: int
    status: Literal["N/D", "detectado"]


class BottlenecksOut(BaseModel):
    signals: list[BottleneckSignalOut]
    method: str = "Extracción determinista de documentos y titulares almacenados"
    limitation: str = "Se requieren al menos dos autores o editores independientes; no implica una recomendación de inversión"


@router.get("", response_model=BottlenecksOut, summary="Listar señales de cuellos de botella")
def list_bottlenecks(db: Session = Depends(get_db)) -> BottlenecksOut:
    tenant = db.info.get("tenant_id")
    rows = {} if not isinstance(tenant, int) else {
        row.theme: row for row in db.scalars(select(BottleneckSignal).where(
            BottleneckSignal.tenant_id == tenant
        ))
    }
    signals = []
    for theme in THEMES:
        row = rows.get(theme)
        signals.append(BottleneckSignalOut(
            theme=theme,
            evidence_ids=row.evidence_ids if row else [],
            first_seen=row.first_seen if row else None,
            last_seen=row.last_seen if row else None,
            n_sources=row.n_sources if row else 0,
            status="detectado" if row and row.n_sources >= 2 else "N/D",
        ))
    return BottlenecksOut(signals=signals)
