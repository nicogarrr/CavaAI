"""Tipos de dominio y contrato de procedencia de cada chunk."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

_NS = uuid.UUID("6f0f1d0e-4b1a-5c53-9a58-0a6f6a1c5e11")


class Corpus(StrEnum):
    EVERGREEN = "evergreen"  # conocimiento atemporal: cartas, libros, memos
    DATED = "dated"  # datos financieros fechados: valen "a fecha X"


class DocType(StrEnum):
    LETTER = "letter"
    BOOK = "book"
    MEMO = "memo"
    ARTICLE = "article"
    TRANSCRIPT = "transcript"
    FILING = "filing"
    DATASET = "dataset"


_DATED_TYPES = {DocType.FILING, DocType.DATASET}

RIGHTS_VALUES = ("public_domain", "open_license", "owner_licensed", "private_use", "unknown")
LANGUAGES = ("en", "es")


class SourceMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class SourceMetadata:
    title: str
    source_uri: str
    language: str
    doc_type: DocType
    rights: str = "unknown"
    author: str | None = None
    published_date: date | None = None
    as_of: date | None = None

    @property
    def corpus(self) -> Corpus:
        return Corpus.DATED if self.doc_type in _DATED_TYPES else Corpus.EVERGREEN

    def validate(self) -> SourceMetadata:
        if not self.title.strip():
            raise SourceMetadataError("title is required")
        if not self.source_uri.strip():
            raise SourceMetadataError("source_uri is required")
        if self.language not in LANGUAGES:
            raise SourceMetadataError(f"language must be one of {LANGUAGES}")
        if self.rights not in RIGHTS_VALUES:
            raise SourceMetadataError(f"rights must be one of {RIGHTS_VALUES}")
        if self.corpus is Corpus.DATED and self.as_of is None:
            raise SourceMetadataError("dated financial data requires as_of")
        if self.corpus is Corpus.EVERGREEN and self.as_of is not None:
            raise SourceMetadataError("as_of is only for dated financial data; use published_date")
        return self


@dataclass(frozen=True)
class BBox:
    page: int
    left: float
    top: float
    right: float
    bottom: float
    origin: str = "BOTTOMLEFT"


@dataclass
class Block:
    """Unidad extraida (parrafo, item de lista, tabla) con su procedencia."""

    text: str
    page: int | None = None
    bbox: BBox | None = None
    kind: str = "paragraph"


@dataclass
class Section:
    heading_path: tuple[str, ...]
    blocks: list[Block] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    sections: list[Section]
    extractor: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParentChunk:
    id: str
    ordinal: int
    text: str
    text_sha256: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None


@dataclass
class ChildChunk:
    id: str
    parent_id: str
    ordinal: int
    text: str  # cita literal: parent.text[char_start:char_end]
    embed_text: str  # prefijo de contexto + texto, <= limite de tokens
    char_start: int
    char_end: int
    text_sha256: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    bboxes: list[BBox]
    token_count: int


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def stable_id(source_sha256: str, *parts: int | str) -> str:
    return str(uuid.uuid5(_NS, ":".join([source_sha256, *map(str, parts)])))


_WS = re.compile(r"\s+")


def normalize_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def payload_for_child(
    child: ChildChunk,
    parent: ParentChunk,
    meta: SourceMetadata,
    *,
    tenant_id: int | None,
    source_id: int,
    source_sha256: str,
    extractor: str,
) -> dict[str, Any]:
    """Payload de Qdrant: procedencia completa + campos filtrables."""
    return {
        "tenant_id": tenant_id,
        "source_id": source_id,
        "source_sha256": source_sha256,
        "parent_id": parent.id,
        "parent_ordinal": parent.ordinal,
        "chunk_ordinal": child.ordinal,
        "text": child.text,
        "text_sha256": child.text_sha256,
        "char_start": child.char_start,
        "char_end": child.char_end,
        "title": meta.title,
        "author": meta.author,
        "author_key": (meta.author or "").strip().lower() or None,
        "source_uri": meta.source_uri,
        "language": meta.language,
        "doc_type": meta.doc_type.value,
        "corpus": meta.corpus.value,
        "rights": meta.rights,
        "published_date": meta.published_date.isoformat() if meta.published_date else None,
        "published_ord": meta.published_date.toordinal() if meta.published_date else None,
        "as_of": meta.as_of.isoformat() if meta.as_of else None,
        "as_of_ord": meta.as_of.toordinal() if meta.as_of else None,
        "section_path": list(child.section_path),
        "page_start": child.page_start,
        "page_end": child.page_end,
        "bboxes": [asdict(b) for b in child.bboxes],
        "extractor": extractor,
    }
