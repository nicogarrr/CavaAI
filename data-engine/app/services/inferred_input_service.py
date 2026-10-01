"""Inputs INFERIDO: estimacion con base explicita y URLs web.

Relajacion acotada de #691: el motor pre-revenue solo calcula escenarios con
un margen FCF inferido cuando este lleva base ("dado X, inferimos Y") y al
menos una URL https. Sin base o sin URL no hay numero (fail closed).
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Company, InferredInput

# clave -> (min exclusivo, max inclusivo) del valor aceptado.
ALLOWED_KEYS: dict[str, tuple[float, float]] = {"fcf_margin": (-1.0, 0.60)}
MIN_BASE_CHARS = 20
MAX_URLS = 10


class InferredInputError(ValueError):
    pass


def clean_urls(urls: list[str]) -> list[str]:
    out: list[str] = []
    for raw in urls:
        url = (raw or "").strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or "." not in parsed.netloc:
            continue
        if url not in out:
            out.append(url)
    return out[:MAX_URLS]


def validate(key: str, value: float | Decimal | None, base: str | None, urls: list[str]) -> list[str]:
    """Devuelve la lista de problemas; vacia = INFERIDO valido."""
    problems: list[str] = []
    if key not in ALLOWED_KEYS:
        return [f"input no inferible: {key}"]
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ["valor no numerico"]
    low, high = ALLOWED_KEYS[key]
    if not (low < number <= high):
        problems.append("valor fuera de rango")
    if len((base or "").strip()) < MIN_BASE_CHARS:
        problems.append("base explicita ausente o demasiado corta")
    if not clean_urls(urls):
        problems.append("falta al menos una URL https")
    return problems


class InferredInputService:
    def create(
        self,
        db: Session,
        company: Company,
        *,
        input_key: str,
        value: Decimal,
        base: str,
        source_urls: list[str],
        origin: str = "llm",
    ) -> InferredInput:
        problems = validate(input_key, value, base, source_urls)
        if problems:
            raise InferredInputError("; ".join(problems))
        row = InferredInput(
            company_id=company.id,
            input_key=input_key,
            value=value,
            base=base.strip(),
            source_urls=clean_urls(source_urls),
            origin=origin,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def latest_valid(self, db: Session, company_id: int, input_key: str) -> InferredInput | None:
        """Ultimo input vigente que sigue siendo valido; el resto se ignora."""
        row = db.scalar(
            select(InferredInput)
            .where(InferredInput.company_id == company_id, InferredInput.input_key == input_key)
            .order_by(desc(InferredInput.id))
            .limit(1)
        )
        if row is None or validate(row.input_key, row.value, row.base, list(row.source_urls or [])):
            return None
        return row


def payload(row: InferredInput) -> dict:
    return {
        "id": row.id,
        "input_key": row.input_key,
        "value": float(row.value),
        "unit": row.unit,
        "base": row.base,
        "source_urls": list(row.source_urls or []),
        "origin": row.origin,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
