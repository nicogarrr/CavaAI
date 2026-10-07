"""Extraccion con Docling (PDF, EPUB, HTML, DOCX, Markdown) -> secciones.

Pipeline MINIMO: sin OCR por defecto, sin VLM, sin ASR, sin enriquecimientos
(formulas, codigo, imagenes). Docling solo corre en worker (carga ~GB de
RAM/modelos); import perezoso. ``.txt`` se lee sin Docling.

Pesos que Docling descarga la primera vez (HuggingFace, cache local):
  * docling-project/docling-layout-heron  ~172 MB  (Apache-2.0)
  * docling-project/docling-models TableFormer fast ~145 MB / accurate ~213 MB
    (CDLA-Permissive-2.0)
Ver docs/knowledge-rag.md.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

from app.services.knowledge_rag.domain import BBox, Block, ExtractedDocument, Section

DOCLING_EXTENSIONS = {".pdf", ".epub", ".html", ".htm", ".xhtml", ".docx", ".md"}
TEXT_EXTENSIONS = {".txt"}
SUPPORTED_EXTENSIONS = DOCLING_EXTENSIONS | TEXT_EXTENSIONS

_SKIP_LABELS = {"page_header", "page_footer", "picture", "page_number"}
_TITLE_LABEL = "title"
_HEADER_LABEL = "section_header"


class ExtractionUnavailable(RuntimeError):
    """Docling no esta instalado: falla alto, no degrada procedencia en silencio."""


class ExtractionError(RuntimeError):
    pass


def build_converter(*, ocr: bool = False, table_mode: str = "fast", artifacts_path: str | None = None) -> Any:
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            TableFormerMode,
            TableStructureOptions,
        )
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except Exception as exc:  # noqa: BLE001
        raise ExtractionUnavailable(f"docling not installed ({type(exc).__name__})") from exc
    options = PdfPipelineOptions()
    options.do_ocr = bool(ocr)
    options.do_table_structure = True
    options.table_structure_options = TableStructureOptions(
        do_cell_matching=True,
        mode=TableFormerMode.ACCURATE if table_mode == "accurate" else TableFormerMode.FAST,
    )
    options.do_picture_classification = False
    options.do_picture_description = False
    options.do_code_enrichment = False
    options.do_formula_enrichment = False
    options.generate_page_images = False
    if artifacts_path:
        options.artifacts_path = artifacts_path
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def extract_file(
    path: Path,
    *,
    converter: Any | None = None,
    ocr: bool = False,
    table_mode: str = "fast",
) -> ExtractedDocument:
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(f"unsupported file type {ext!r}")
    if ext in TEXT_EXTENSIONS:
        return extract_plain_text(path.read_text(encoding="utf-8", errors="replace"))
    conv = converter or build_converter(
        ocr=ocr, table_mode=table_mode, artifacts_path=os.environ.get("DOCLING_ARTIFACTS_PATH")
    )
    try:
        result = conv.convert(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"docling failed ({type(exc).__name__}: {exc})") from exc
    doc = getattr(result, "document", None)
    if doc is None:
        raise ExtractionError("docling returned no document")
    return sections_from_docling(doc)


def extract_bytes(content: bytes, filename: str, **kwargs: Any) -> ExtractedDocument:
    suffix = Path(filename).suffix.lower() or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(content)
        tmp = Path(handle.name)
    try:
        return extract_file(tmp, **kwargs)
    finally:
        tmp.unlink(missing_ok=True)


def extract_plain_text(text: str) -> ExtractedDocument:
    blocks = [Block(p.strip()) for p in re.split(r"\n\s*\n", text) if p.strip()]
    return ExtractedDocument(
        sections=[Section((), blocks)] if blocks else [],
        extractor="plaintext",
        warnings=["plain text has no headings, pages or bboxes"],
    )


def _label(item: Any) -> str:
    label = getattr(item, "label", None)
    return str(getattr(label, "value", label) or "").lower()


def _prov(item: Any) -> tuple[int | None, BBox | None]:
    for entry in getattr(item, "prov", None) or []:
        page = getattr(entry, "page_no", None)
        box = getattr(entry, "bbox", None)
        bbox = None
        if box is not None and isinstance(page, int):
            origin = getattr(getattr(box, "coord_origin", None), "value", None) or "BOTTOMLEFT"
            bbox = BBox(page, float(box.l), float(box.t), float(box.r), float(box.b), str(origin))
        return (page if isinstance(page, int) else None), bbox
    return None, None


def sections_from_docling(doc: Any) -> ExtractedDocument:
    """Recorre el DoclingDocument y agrupa bloques bajo su ruta de encabezados."""
    stack: list[tuple[int, str]] = []
    sections: list[Section] = []
    current = Section(())
    warnings: list[str] = []

    def flush() -> None:
        nonlocal current
        if current.blocks:
            sections.append(current)

    iterate: Any = getattr(doc, "iterate_items", None)
    if not callable(iterate):
        raise ExtractionError("docling document is not iterable")
    items: Any = iterate()
    for item, _level in items:
        label = _label(item)
        if label in _SKIP_LABELS:
            continue
        if label in (_TITLE_LABEL, _HEADER_LABEL):
            heading = (getattr(item, "text", "") or "").strip()
            if not heading:
                continue
            depth = 0 if label == _TITLE_LABEL else max(int(getattr(item, "level", 1) or 1), 1)
            flush()
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, heading))
            current = Section(tuple(h for _, h in stack))
            continue
        page, bbox = _prov(item)
        if "table" in label:
            try:
                text = item.export_to_markdown(doc=doc).strip()
            except Exception:  # noqa: BLE001
                warnings.append("table export failed; table skipped")
                continue
            kind = "table"
        else:
            text = (getattr(item, "text", None) or "").strip()
            kind = "list_item" if "list" in label else "paragraph"
        if text:
            current.blocks.append(Block(text, page, bbox, kind))
    flush()
    if not sections:
        raise ExtractionError("docling extracted no text")
    return ExtractedDocument(sections=sections, extractor="docling", warnings=warnings)
