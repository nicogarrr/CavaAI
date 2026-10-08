"""Persistencia del RAG de conocimiento profesional.

Dos tablas. ``KnowledgeRagSource`` es el registro de fuentes (checksum para
dedupe + estado del trabajo + metadatos de procedencia). ``KnowledgeRagParent``
guarda el texto del bloque padre: los vectores viven en Qdrant solo para los
chunks hijos cortos, y el padre (contexto ampliado y base de verificacion de
citas) se guarda aqui para no duplicarlo en cada payload del indice.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import TenantOwnedMixin, TimestampMixin

SOURCE_STATUS_QUEUED = "queued"
SOURCE_STATUS_PROCESSING = "processing"
SOURCE_STATUS_INDEXED = "indexed"
SOURCE_STATUS_FAILED = "failed"


class KnowledgeRagSource(TenantOwnedMixin, Base, TimestampMixin):
    __tablename__ = "knowledge_rag_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sha256", name="uq_knowledge_rag_sources_tenant_sha"),
        Index("ix_knowledge_rag_sources_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_uri: Mapped[str] = mapped_column(String(1000))
    filename: Mapped[str] = mapped_column(String(300))
    published_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    language: Mapped[str] = mapped_column(String(8))
    doc_type: Mapped[str] = mapped_column(String(32))
    corpus: Mapped[str] = mapped_column(String(16))
    rights: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default=SOURCE_STATUS_QUEUED)
    extractor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeRagParent(TenantOwnedMixin, Base):
    __tablename__ = "knowledge_rag_parents"
    __table_args__ = (Index("ix_knowledge_rag_parents_source", "source_id", "ordinal"),)

    # UUID5 determinista (sha256 + ordinal): reingestar no duplica ni cambia ids.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("knowledge_rag_sources.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    section_path: Mapped[list] = mapped_column(JSON, default=list)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
