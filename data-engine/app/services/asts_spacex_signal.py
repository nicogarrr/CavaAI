"""Senal de vigilancia ASTS: SpaceX/Starlink cierra acuerdo con una operadora.

Regla deterministica sobre titulares ya persistidos y citados: sin LLM, sin
cifras y sin inventar enlaces. Un titular no confirma por si solo los hechos:
la alerta es un puntero a la fuente para revision del usuario. Si SpaceX cierra
acuerdos con operadoras grandes, el argumento de que el foso de AST son sus
acuerdos con operadoras se debilita.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, NewsEvent, Position, ResearchAlert, WatchItem
from app.services.tracked_news_alerts import _valid_source_url

VERSION = "asts-spacex-mno-v1"
ALERT_TYPE = "asts_spacex_mno_signal"
MAX_AGE = timedelta(hours=72)
# Listas cerradas. Un termino fuera de ellas no dispara nada.
_SPACEX = r"(?:spacex|starlink(?:\s+mobile)?)"
_MNOS = (
    r"(?:at&t|verizon|t-mobile|tmobile|vodafone|orange\s+(?:sa|france)|telef[oó]nica|movistar|"
    r"deutsche\s+telekom|telstra|optus|rogers|bell\s+canada|rakuten|kddi|ntt|softbank|"
    r"airtel|reliance\s+jio|am[eé]rica\s+m[oó]vil|telcel|telenor|swisscom|"
    r"liberty\s+global|echostar|bouygues|iliad|telecom\s+italia|tim\s+brasil|telus)"
)
_DEAL = (
    r"(?:agreement|agrees?|agreed|deal|partner(?:s|ship|ed)?|signs?|signed|contract|"
    r"acuerdo|alianza|firma(?:n|do)?)"
)
# Hueco corto sin puntuacion de frase: actor y operadora en la misma oracion,
# con el verbo de acuerdo entre ambos (en cualquiera de los dos ordenes).
_GAP = r"[^.;:!?]{0,80}?"
_RE_FORWARD = re.compile(rf"\b{_SPACEX}\b{_GAP}\b{_DEAL}\b{_GAP}(?<![\w]){_MNOS}(?![\w])", re.IGNORECASE)
_RE_REVERSE = re.compile(rf"(?<![\w]){_MNOS}(?![\w]){_GAP}\b{_DEAL}\b{_GAP}\b{_SPACEX}\b", re.IGNORECASE)
# Negaciones, cancelaciones, planes o rumores: no son un acuerdo cerrado.
_RE_NOT_CLOSED = re.compile(
    r"\b(?:den(?:y|ies|ied)|no|not|never|cancel(?:s|led|ed|ls)?|terminat\w*|collaps\w*|"
    r"talks?|negotiat\w*|plans?|planning|could|may|might|would|reportedly|rumou?rs?|"
    r"seeks?|eyes?|considers?|considering|fails?|failed|rejects?|rejected|drops?|dropped|ends?|ended|"
    r"niega|negó|cancela|cancelad[oa]|rechaza|conversaciones|negocia\w*|planea|podr[ií]a|rumor\w*|"
    r"sin acuerdo)\b",
    re.IGNORECASE,
)
# Acuerdos de la propia AST: no son la senal (es el argumento que se vigila).
_RE_AST = re.compile(r"\b(?:ast\s+spacemobile|ast\s+space\s+mobile|asts|ast)\b", re.IGNORECASE)


def matches(headline: str | None) -> bool:
    """Actor SpaceX/Starlink + operadora de la lista con verbo de acuerdo entre
    ambos, sin negaciones/cancelaciones/planes y sin AST en el titular."""
    if not headline or not isinstance(headline, str):
        return False
    if _RE_AST.search(headline) or _RE_NOT_CLOSED.search(headline):
        return False
    return bool(_RE_FORWARD.search(headline) or _RE_REVERSE.search(headline))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def evaluate(db: Session, *, now: datetime | None = None) -> dict:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    now = now or datetime.now(UTC)
    stats = {"examined": 0, "created": 0, "duplicates": 0, "skipped": 0}
    asts = db.scalar(select(Company).where(Company.ticker == "ASTS"))
    if asts is None:
        return stats
    held = db.scalar(select(Position.id).where(Position.company_id == asts.id, Position.quantity > 0).limit(1))
    watched = db.scalar(select(WatchItem.id).where(WatchItem.symbol == "ASTS").limit(1))
    if held is None and watched is None:
        return stats
    spcx = db.scalar(select(Company).where(Company.ticker == "SPCX"))
    company_ids = [asts.id] + ([spcx.id] if spcx else [])
    since = now - MAX_AGE
    rows = db.scalars(select(NewsEvent).where(
        NewsEvent.tenant_id == tenant_id, NewsEvent.company_id.in_(company_ids),
        NewsEvent.date >= since, NewsEvent.date <= now, NewsEvent.url.is_not(None),
    ).order_by(desc(NewsEvent.date)).limit(500)).all()
    for event in rows:
        stats["examined"] += 1
        meta = event.metadata_ or {}
        # Solo el titular textual del conector: sin fallback a event.title
        # (puede ser un resumen del pipeline no verificable).
        headline = meta.get("source_headline")
        url = _valid_source_url(event.url)
        # Misma procedencia que tracked_news: solo conectores de confianza y
        # fecha de la fuente o primera deteccion de GDELT.
        date_source = meta.get("date_source")
        # Filas GDELT antiguas dicen `source` aunque seendate es primera
        # deteccion, no publicacion: no se mezclan (igual que tracked_news).
        if meta.get("connector") == "gdelt" and date_source == "source":
            date_source = "gdelt_first_seen"
        if (not url or not (event.source or "").strip()
                or meta.get("connector") not in {"gdelt", "rss", "ir", "sec"}
                or date_source not in {"source", "gdelt_first_seen"}
                or not isinstance(headline, str) or not matches(headline)):
            stats["skipped"] += 1
            continue
        fp = hashlib.sha256(f"{VERSION}|{tenant_id}|{url}".encode()).hexdigest()
        if db.scalar(select(ResearchAlert.id).where(
                ResearchAlert.tenant_id == tenant_id, ResearchAlert.fingerprint == fp)) is not None:
            stats["duplicates"] += 1
            continue
        published = _aware(event.date)
        headline = headline.strip()
        date_phrase = (f"detectado por GDELT el {published.date().isoformat()}" if date_source == "gdelt_first_seen"
                       else f"fechado el {published.date().isoformat()} por la fuente")
        alert = ResearchAlert(
            tenant_id=tenant_id, company_id=asts.id, severity="high", status="open",
            alert_type=ALERT_TYPE, title=f"Señal ASTS: {headline}"[:300],
            message=(f"Artículo de {event.source}, {date_phrase}: {headline}. "
                     "Señal de vigilancia: si SpaceX cierra acuerdos con operadoras grandes, "
                     "el argumento de que el foso de AST son sus acuerdos con operadoras se debilita. "
                     "Revisa la fuente; el titular no confirma por sí solo los hechos."),
            fingerprint=fp, channels=["in_app"], last_triggered_at=now,
            metadata_={"news_event_id": event.id, "source_url": url, "source": event.source,
                       "published_at": published.isoformat(), "rule_version": VERSION,
                       "date_label": "detectada por GDELT" if date_source == "gdelt_first_seen" else "fechada por la fuente",
                       "date_source": date_source, "source_headline": headline},
        )
        try:
            with db.begin_nested():
                db.add(alert)
                db.flush()
        except IntegrityError:
            stats["duplicates"] += 1
            continue
        db.commit()
        stats["created"] += 1
    return stats
