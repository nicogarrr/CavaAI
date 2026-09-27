"""Bounded, tenant-scoped analysis of a gated in-app news alert.

An attributed headline is not independent verification. This first pipeline
stores an honest baseline; later primary-record analysis can append a version.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models import AlertAnalysis, NewsEvent, ResearchAlert
from app.services.research_assistant_service import _url

VERSION = "headline-baseline-v1"
DAILY_LIMIT = 20


def queue_analysis(db: Session, alert: ResearchAlert) -> AlertAnalysis | None:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None or alert.tenant_id != tenant_id or alert.alert_type != "tracked_news":
        raise ValueError("Tenant-scoped tracked-news alert required")
    event_id = (alert.metadata_ or {}).get("news_event_id")
    event = db.scalar(select(NewsEvent).where(NewsEvent.id == event_id, NewsEvent.company_id == alert.company_id))
    if (event is None or not _url(event.url) or
            not isinstance((event.metadata_ or {}).get("source_headline"), str) or
            not (event.metadata_ or {})["source_headline"].strip()):
        return None
    existing = db.scalar(select(AlertAnalysis).where(
        AlertAnalysis.tenant_id == tenant_id, AlertAnalysis.alert_id == alert.id,
        AlertAnalysis.version == VERSION))
    if existing:
        return existing
    today = datetime.now(UTC).date()
    count = db.scalar(select(func.count(AlertAnalysis.id)).where(
        AlertAnalysis.tenant_id == tenant_id,
        AlertAnalysis.created_at >= datetime(today.year, today.month, today.day, tzinfo=UTC),
    )) or 0
    status = "pending" if count < DAILY_LIMIT else "insufficient_data"
    row = AlertAnalysis(tenant_id=tenant_id, alert_id=alert.id, news_event_id=event.id,
                        version=VERSION, status=status,
                        result={} if status == "pending" else {
                            "sections": [{"key": "insufficient_data", "body": "Límite diario de análisis alcanzado; fuente primaria no consultada.", "citation_ids": []}],
                            "citations": [], "writeback": False,
                        })
    db.add(row)
    db.commit()
    return row


def reconcile_missing_analyses(db: Session, *, limit: int = 50) -> dict:
    """Queue analyses for tracked_news alerts that never got a row.

    Independent of NewsEvent eligibility (no MAX_AGE gate): the per-alert
    repair in evaluate() only runs while the event still passes the
    eligibility filter, so a lost row whose event aged out would never be
    recovered. queue_analysis remains the honest gate: no event, no valid
    URL, or no original headline means no row.

    The candidate SELECT pre-filters in SQL the rows that can never pass
    that gate (no matching event, no http(s) URL, no non-empty source
    headline). But the SQL approximation cannot express the full gate: a
    URL like "https://" without host, a userinfo URL, a tab-padded or
    non-string JSON headline all pass the filter and fail the gate
    forever. Fifty of those ahead by ID would starve the batch exactly
    like the unfiltered version. So a deterministic gate failure
    (queue_analysis returning None with the event present) leaves a
    durable exclusion mark on the alert with the exact content it failed
    on (url + source_headline). The candidate filter skips a marked
    alert only while the event content still matches the mark: fixing
    the URL or headline makes the row a candidate again automatically,
    which is the retry path on data correction. A missing event needs no
    mark: the EXISTS pre-filter already excludes it. Exceptions
    (transient failures) never mark. A successful queue clears any stale
    mark. queue_analysis stays the authoritative gate; the mark is only
    bookkeeping on top of it.
    """
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    if db.get_bind().dialect.name == "postgresql":
        id_match = cast(NewsEvent.id, String) == ResearchAlert.metadata_["news_event_id"].as_string()
    else:  # SQLite: json_extract devuelve el entero nativo; texto malformado no coincide ni rompe
        id_match = NewsEvent.id == ResearchAlert.metadata_["news_event_id"]
    url_norm = func.lower(func.trim(NewsEvent.url))
    queueable_event = (
        select(NewsEvent.id)
        .where(
            id_match,
            NewsEvent.company_id == ResearchAlert.company_id,
            or_(url_norm.like("http://%"), url_norm.like("https://%")),
            func.length(func.trim(NewsEvent.url)) >= 8,
            func.length(func.trim(NewsEvent.metadata_["source_headline"].as_string())) > 0,
            or_(
                ResearchAlert.metadata_["analysis_excluded_url"].as_string().is_(None),
                ResearchAlert.metadata_["analysis_excluded_url"].as_string() != NewsEvent.url,
                ResearchAlert.metadata_["analysis_excluded_headline"].as_string()
                != NewsEvent.metadata_["source_headline"].as_string(),
            ),
        )
        .exists()
    )
    base_filters = (
        ResearchAlert.tenant_id == tenant_id,
        ResearchAlert.alert_type == "tracked_news",
        ~select(AlertAnalysis.id)
        .where(
            AlertAnalysis.tenant_id == tenant_id,
            AlertAnalysis.alert_id == ResearchAlert.id,
            AlertAnalysis.version == VERSION,
        )
        .exists(),
    )
    missing = db.scalars(
        select(ResearchAlert).where(*base_filters, queueable_event)
        .order_by(ResearchAlert.id).limit(limit)
    ).all()
    excluded = db.scalar(
        select(func.count(ResearchAlert.id)).where(*base_filters, ~queueable_event)
    ) or 0
    stats = {"examined": len(missing), "queued": 0, "unqueueable": 0,
             "excluded_no_data": excluded, "marked": 0}
    for alert in missing:
        try:
            row = queue_analysis(db, alert)
        except Exception:
            db.rollback()  # transitorio: jamas marca
            stats["unqueueable"] += 1
            continue
        if row is None:
            stats["unqueueable"] += 1
            event = db.scalar(select(NewsEvent).where(
                NewsEvent.id == (alert.metadata_ or {}).get("news_event_id")))
            if event is not None:
                # Fallo determinista del gate: marca durable con el contenido
                # exacto que fallo; si el dato se corrige, la marca deja de
                # coincidir y la alerta reingresa sola.
                alert.metadata_ = {
                    **(alert.metadata_ or {}),
                    "analysis_excluded_url": event.url,
                    "analysis_excluded_headline": (event.metadata_ or {}).get("source_headline"),
                }
                stats["marked"] += 1
        else:
            stats["queued"] += 1
            meta = alert.metadata_ or {}
            if "analysis_excluded_url" in meta:
                alert.metadata_ = {k: v for k, v in meta.items()
                                   if not k.startswith("analysis_excluded_")}
    db.commit()
    return stats


def analyze_alert(db: Session, alert_id: int) -> dict:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise ValueError("Tenant context required")
    analysis = db.scalar(select(AlertAnalysis).where(
        AlertAnalysis.tenant_id == tenant_id, AlertAnalysis.alert_id == alert_id,
        AlertAnalysis.version == VERSION).with_for_update())
    if analysis is None:
        raise LookupError("Alert analysis not queued for this tenant")
    if analysis.status != "pending":
        return {"status": analysis.status, "analysis_id": analysis.id}
    alert = db.scalar(select(ResearchAlert).where(ResearchAlert.id == alert_id,
                                                   ResearchAlert.alert_type == "tracked_news"))
    event = db.scalar(select(NewsEvent).where(NewsEvent.id == analysis.news_event_id))
    headline = (event.metadata_ or {}).get("source_headline") if event else None
    if (alert is None or event is None or event.company_id != alert.company_id or
            (alert.metadata_ or {}).get("news_event_id") != event.id or
            not isinstance(headline, str) or not headline.strip() or not _url(event.url)):
        analysis.status = "insufficient_data"
        analysis.result = {"sections": [{"key": "insufficient_data", "body": "No hay titular original y enlace verificables.", "citation_ids": []}],
                           "citations": [], "writeback": False}
    else:
        provenance = event.metadata_ or {}
        date_source = provenance.get("date_source")
        if provenance.get("connector") == "gdelt" and date_source == "source":
            date_source = "gdelt_first_seen"  # legacy GDELT seendate is first-seen
        date_label = ("primera detección GDELT" if date_source == "gdelt_first_seen"
                      else "fecha atribuida a la fuente" if date_source == "source"
                      else "fecha sin procedencia confirmada")
        citation = {"id": f"news_event:{event.id}", "kind": "news_event",
                    "source": event.source, "url": event.url,
                    "as_of": f"{event.date.isoformat()} ({date_label})", "excerpt": headline.strip()[:500]}
        analysis.status = "insufficient_data"
        analysis.result = {"sections": [
            {"key": "facts", "body": f"Titular atribuido a {event.source}: {citation['excerpt']}", "citation_ids": [citation["id"]]},
            {"key": "insufficient_data", "body": "Fuente primaria no consultada. El titular no verifica el hecho ni su impacto para inversores.", "citation_ids": []}],
            "citations": [citation], "writeback": False}
    db.commit()
    return {"status": analysis.status, "analysis_id": analysis.id}


def read_analysis(db: Session, alert_id: int) -> dict:
    tenant_id = db.info.get("tenant_id")
    if tenant_id is None:
        raise LookupError("Tenant context required")
    alert = db.scalar(select(ResearchAlert).where(ResearchAlert.id == alert_id,
                                                   ResearchAlert.tenant_id == tenant_id))
    if alert is None:
        raise LookupError("Alert not found")
    rows = db.scalars(select(AlertAnalysis).where(
        AlertAnalysis.tenant_id == tenant_id, AlertAnalysis.alert_id == alert_id,
    ).order_by(AlertAnalysis.id)).all()
    versions = []
    for row in rows:
        result = row.result or {}
        event = db.scalar(select(NewsEvent).where(NewsEvent.id == row.news_event_id))
        citations = result.get("citations", [])
        headline = (event.metadata_ or {}).get("source_headline") if event else None
        valid = (isinstance(headline, str) and bool(headline.strip()) and
                 isinstance(citations, list) and event.company_id == alert.company_id and
                 (alert.metadata_ or {}).get("news_event_id") == event.id and
                 all(c.get("id") == f"news_event:{event.id}" and
                     c.get("url") == event.url and
                     c.get("source") == event.source and
                     event.date.isoformat() in c.get("as_of", "") and
                     c.get("excerpt") == headline.strip()[:500]
                     for c in citations))
        if not valid:
            versions.append({"id": row.id, "version": row.version, "status": "insufficient_data",
                             "sections": [], "citations": [], "missing_data": ["La cita ya no se pudo validar."],
                             "writeback": False})
        else:
            versions.append({"id": row.id, "version": row.version, "status": row.status,
                             "sections": result.get("sections", []), "citations": citations,
                             "missing_data": ["Fuente primaria no consultada."], "writeback": False})
    return {"alert_id": alert_id, "versions": versions}
