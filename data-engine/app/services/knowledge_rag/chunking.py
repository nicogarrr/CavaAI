"""Chunking padre/hijo por seccion, consciente del tokenizer.

Hijos: cortos (<= ``child_max_tokens`` wordpieces INCLUIDO el prefijo de
contexto y los tokens especiales) para que MiniLM no los trunque. Padres:
ventanas contiguas de la misma seccion para ampliar contexto despues. El texto
de cada hijo es literalmente ``parent.text[char_start:char_end]``, que es lo que
hace verificable la cita.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.knowledge_rag.domain import (
    BBox,
    Block,
    ChildChunk,
    ExtractedDocument,
    ParentChunk,
    Section,
    sha256_hex,
    stable_id,
)
from app.services.knowledge_rag.tokens import TokenCounter

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[\"'“¿¡(\[]?[A-ZÁÉÍÓÚÑÜ0-9])")
_PREFIX_MAX_TOKENS = 24


@dataclass(frozen=True)
class ChunkConfig:
    child_max_tokens: int = 200
    child_overlap_tokens: int = 30
    parent_max_tokens: int = 900

    def __post_init__(self) -> None:
        if self.child_overlap_tokens >= self.child_max_tokens // 2:
            raise ValueError("child_overlap_tokens must be < child_max_tokens / 2")
        if self.parent_max_tokens < 2 * self.child_max_tokens:
            raise ValueError("parent_max_tokens must be >= 2 * child_max_tokens")


@dataclass
class _Unit:
    start: int  # offsets absolutos en el texto de la seccion
    end: int
    tokens: int
    block_index: int


def _section_text(section: Section) -> tuple[str, list[tuple[int, int]]]:
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for block in section.blocks:
        text = block.text.strip()
        if not text:
            spans.append((pos, pos))
            continue
        if parts:
            pos += 2  # separador "\n\n"
        spans.append((pos, pos + len(text)))
        parts.append(text)
        pos += len(text)
    return "\n\n".join(parts), spans


def _split_sentences(text: str, base: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _SENTENCE_END.finditer(text):
        spans.append((base + cursor, base + match.start()))
        cursor = match.end()
    spans.append((base + cursor, base + len(text)))
    return [(s, e) for s, e in spans if e > s]


class ChunkingError(ValueError):
    """Un chunk no cabe en su limite de tokens: se falla alto, nunca se trunca."""


def _split_long_word(word: str, base: int, budget: int, count: TokenCounter) -> list[tuple[int, int]]:
    """Parte una 'palabra' sin espacios por caracteres (biseccion con el contador)."""
    out: list[tuple[int, int]] = []
    pos = 0
    while pos < len(word):
        lo, hi = 1, len(word) - pos
        while lo < hi:  # mayor prefijo que cabe en budget
            mid = (lo + hi + 1) // 2
            if count(word[pos : pos + mid]) <= budget + 2:
                lo = mid
            else:
                hi = mid - 1
        if count(word[pos : pos + lo]) > budget + 2:
            raise ChunkingError("a single character exceeds the child token budget")
        out.append((base + pos, base + pos + lo))
        pos += lo
    return out


def _hard_split(text: str, base: int, budget: int, count: TokenCounter) -> list[tuple[int, int]]:
    """Parte una unidad enorme por palabras y, si una palabra sola no cabe, por caracteres."""
    pieces: list[tuple[int, int]] = []
    for m in re.finditer(r"\S+", text):
        if count(m.group()) - 2 > budget:
            pieces.extend(_split_long_word(m.group(), base + m.start(), budget, count))
        else:
            pieces.append((base + m.start(), base + m.end()))
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(pieces):
        j = i + 1
        while j < len(pieces) and count(text[pieces[i][0] - base : pieces[j][1] - base]) - 2 <= budget:
            j += 1
        out.append((pieces[i][0], pieces[j - 1][1]))
        i = j
    return out


def _units(section_text: str, spans: list[tuple[int, int]], budget: int, count: TokenCounter) -> list[_Unit]:
    units: list[_Unit] = []
    for index, (b_start, b_end) in enumerate(spans):
        if b_end <= b_start:
            continue
        block_text = section_text[b_start:b_end]
        pieces = _split_sentences(block_text, b_start)
        if section_text[b_start:b_end].count("\n") >= 2 and "|" in block_text:
            # tabla en markdown: una unidad por fila
            pieces = [
                (b_start + m.start(), b_start + m.end())
                for m in re.finditer(r"[^\n]+", block_text)
            ]
        for p_start, p_end in pieces:
            tokens = count(section_text[p_start:p_end]) - 2
            if tokens > budget:
                for h_start, h_end in _hard_split(section_text[p_start:p_end], p_start, budget, count):
                    units.append(_Unit(h_start, h_end, count(section_text[h_start:h_end]) - 2, index))
            else:
                units.append(_Unit(p_start, p_end, max(tokens, 1), index))
    return units


def _context_prefix(title: str, path: tuple[str, ...], count: TokenCounter) -> str:
    label = " > ".join([title, *path[-2:]]) if path else title
    words = label.split()
    while words and count(" ".join(words) + ": ") > _PREFIX_MAX_TOKENS:
        words.pop()
    return (" ".join(words) + ": ") if words else ""


def _union_bboxes(blocks: list[Block]) -> list[BBox]:
    return [b.bbox for b in blocks if b.bbox is not None]


def chunk_document(
    doc: ExtractedDocument,
    *,
    title: str,
    source_sha256: str,
    count: TokenCounter,
    config: ChunkConfig | None = None,
    id_namespace: str | None = None,
) -> tuple[list[ParentChunk], list[ChildChunk]]:
    """``id_namespace`` (p. ej. ``tenant:source_id:sha``) evita que dos tenants con los
    mismos bytes compartan ids de padres (PK SQL) y puntos de Qdrant."""
    cfg = config or ChunkConfig()
    ns = id_namespace or source_sha256
    parents: list[ParentChunk] = []
    children: list[ChildChunk] = []
    for section in doc.sections:
        text, spans = _section_text(section)
        if not text.strip():
            continue
        prefix = _context_prefix(title, section.heading_path, count)
        budget = cfg.child_max_tokens - count(prefix) if prefix else cfg.child_max_tokens
        budget = max(budget - 2, 16)  # [CLS]/[SEP] ya van en count(); margen
        units = _units(text, spans, budget, count)
        ranges = _pack_children(units, text, prefix, cfg, count, budget)
        for group in _group_parents(ranges, text, cfg, count):
            ordinal = len(parents)
            p_start, p_end = group[0][0], group[-1][1]
            p_text = text[p_start:p_end]
            pid = stable_id(ns, "p", ordinal)
            blocks = [section.blocks[i] for i in _block_indexes(spans, p_start, p_end)]
            pages = [b.page for b in blocks if b.page is not None]
            parents.append(
                ParentChunk(
                    id=pid,
                    ordinal=ordinal,
                    text=p_text,
                    text_sha256=sha256_hex(p_text),
                    section_path=section.heading_path,
                    page_start=min(pages) if pages else None,
                    page_end=max(pages) if pages else None,
                )
            )
            for c_start, c_end in group:
                c_text = text[c_start:c_end]
                c_blocks = [section.blocks[i] for i in _block_indexes(spans, c_start, c_end)]
                c_pages = [b.page for b in c_blocks if b.page is not None]
                embed_text = prefix + c_text
                children.append(
                    ChildChunk(
                        id=stable_id(ns, "c", ordinal, len(children)),
                        parent_id=pid,
                        ordinal=len(children),
                        text=c_text,
                        embed_text=embed_text,
                        char_start=c_start - p_start,
                        char_end=c_end - p_start,
                        text_sha256=sha256_hex(c_text),
                        section_path=section.heading_path,
                        page_start=min(c_pages) if c_pages else None,
                        page_end=max(c_pages) if c_pages else None,
                        bboxes=_union_bboxes(c_blocks),
                        token_count=count(embed_text),
                    )
                )
    for child in children:
        if child.token_count > cfg.child_max_tokens:
            raise ChunkingError(
                f"child chunk {child.ordinal} has {child.token_count} tokens (> {cfg.child_max_tokens})"
            )
    for parent in parents:
        if count(parent.text) > cfg.parent_max_tokens:
            raise ChunkingError(
                f"parent chunk {parent.ordinal} has {count(parent.text)} tokens (> {cfg.parent_max_tokens})"
            )
    return parents, children


def _block_indexes(spans: list[tuple[int, int]], start: int, end: int) -> list[int]:
    return [i for i, (s, e) in enumerate(spans) if e > s and s < end and e > start]


def _pack_children(
    units: list[_Unit],
    text: str,
    prefix: str,
    cfg: ChunkConfig,
    count: TokenCounter,
    budget: int,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    i = 0
    n = len(units)
    limit = cfg.child_max_tokens
    while i < n:
        j = i
        used = 0
        while j < n and used + units[j].tokens <= budget:
            used += units[j].tokens
            j += 1
        if j == i:
            j = i + 1  # una unidad nunca cabe: se emite sola (ya hard-split)
        # verificacion EXACTA; si el conteo aditivo se queda corto, recorta
        while j - i > 1 and count(prefix + text[units[i].start : units[j - 1].end]) > limit:
            j -= 1
        ranges.append((units[i].start, units[j - 1].end))
        if j >= n:
            break
        # solapamiento: retrocede unidades hasta ~overlap tokens, sin repetir todo
        back = j
        acc = 0
        while back > i + 1 and acc + units[back - 1].tokens <= cfg.child_overlap_tokens:
            acc += units[back - 1].tokens
            back -= 1
        i = back if back > i else j
    return ranges


def _group_parents(
    ranges: list[tuple[int, int]], text: str, cfg: ChunkConfig, count: TokenCounter
) -> list[list[tuple[int, int]]]:
    groups: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    for rng in ranges:
        if current and count(text[current[0][0] : rng[1]]) > cfg.parent_max_tokens:
            groups.append(current)
            current = []
        current.append(rng)
    if current:
        groups.append(current)
    return groups
