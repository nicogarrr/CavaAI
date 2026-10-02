"""HTML filing -> markdown con seccion y pagina para el pipeline de documentos.

Contrato de entrada de ``document_ingestion_service`` (solo lectura, no se
cambia): ``_chunk_blocks`` acepta bloques con ``.text`` y ``.metadata``
(dict que viaja a ``chunk.metadata_["block_metadata"]``); ``_parse_html``
usa ``native_html`` y pierde secciones. Esta via produce bloques con:

- ``metadata["section"]``: ultima cabecera markdown o Item SEC detectado
  (``ITEM 1A. RISK FACTORS``, ``ITEM 7. MANAGEMENT'S DISCUSSION...``,
  normalizados a ``Risk Factors`` / ``MD&A`` entre otros). La provenance de
  Fase B1 cita seccion + pagina sin re-parsear.
- ``metadata["page"]``: ordinal 1-based del bloque (los filings EDGAR no
  traen paginas reales; el markdown de ``Filing.markdown()`` tampoco las
  numera salvo el modo legacy deprecado, asi que pagina = chunk secuencial,
  declarado y auditable).
- ``metadata["source"]`` = ``"edgartools"`` y ``metadata["format"]`` =
  ``"markdown"``.

La conversion HTML->markdown es propia y minima (cabeceras, parrafos,
tablas a pipe-markdown, listas): en live se prefiere ``Filing.markdown()``
de edgartools (tablas/imagenes del pipeline ``edgar.documents``) y este
modulo solo secciona y pagina.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

MAX_BLOCK_CHARS = 2500

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
_ITEM_RE = re.compile(r"^\s*ITEM\s+([0-9A-Z]+)[.\s]+(.*)$", re.IGNORECASE)

_ITEM_LABELS = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety",
    "5": "Market for Registrant's Common Equity",
    "6": "Selected Financial Data",
    "7": "MD&A",
    "7A": "Market Risk Disclosures",
    "8": "Financial Statements",
    "9": "Changes in Accountants",
    "9A": "Controls and Procedures",
    "10": "Directors and Executive Officers",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Related Party Transactions",
    "14": "Accountant Fees",
    "15": "Exhibits",
}


@dataclass
class MarkdownBlock:
    """Compatible con ``ParsedBlock`` (``.text`` + ``.metadata`` dict)."""

    text: str
    metadata: dict = field(default_factory=dict)


def detect_section(line: str) -> str | None:
    """Seccion de una linea markdown (cabecera o Item SEC), o None."""
    heading = _HEADING_RE.match(line)
    text = heading.group(2) if heading else line
    item = _ITEM_RE.match(text.strip())
    if item:
        code = item.group(1).upper()
        rest = item.group(2).strip()
        label = _ITEM_LABELS.get(code, rest)
        if code in ("1A", "7") or not rest:
            return label
        return f"{label} — {rest}" if label != rest else rest
    if heading:
        return text.strip()
    return None


def split_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    """``[(seccion, texto)]`` partiendo por cabeceras/Items (orden original)."""
    sections: list[tuple[str, list[str]]] = []
    current = "Document"
    buffer: list[str] = []
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        section = detect_section(raw_line)
        if section is not None and raw_line.strip():
            if buffer and any(line.strip() for line in buffer):
                sections.append((current, buffer))
            current, buffer = section, [raw_line]
        else:
            buffer.append(raw_line)
    if buffer and any(line.strip() for line in buffer):
        sections.append((current, buffer))
    return [(name, "\n".join(lines).strip()) for name, lines in sections]


def markdown_blocks(markdown: str, *, max_chars: int = MAX_BLOCK_CHARS) -> list[MarkdownBlock]:
    """Bloques con ``section`` + ``page`` (pagina = ordinal secuencial)."""
    blocks: list[MarkdownBlock] = []
    page = 0
    for section, text in split_markdown_sections(markdown):
        words = text.split()
        piece: list[str] = []
        length = 0
        chunks: list[str] = []
        for word in words:
            if length + len(word) + 1 > max_chars and piece:
                chunks.append(" ".join(piece))
                piece, length = [], 0
            piece.append(word)
            length += len(word) + 1
        if piece:
            chunks.append(" ".join(piece))
        for chunk in chunks:
            page += 1
            blocks.append(
                MarkdownBlock(
                    text=chunk,
                    metadata={"section": section, "page": page, "source": "edgartools", "format": "markdown"},
                )
            )
    return blocks


class _SimpleHTMLToMarkdown(HTMLParser):
    """HTML->markdown minimo (fallback cuando no hay ``Filing.markdown()``)."""

    def __init__(self) -> None:
        super().__init__()
        self._out: list[str] = []
        self._cell: list[str] | None = None
        self._row: list[str] | None = None
        self._in_cell = False
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = True
            self._out.append("## ")
        elif tag == "p":
            self._out.append("\n\n")
        elif tag == "br":
            self._out.append("\n")
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._in_cell = True
        elif tag == "li":
            self._out.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("h1", "h2", "h3", "h4"):
            self._in_heading = False
            self._out.append("\n")
        elif tag in ("td", "th"):
            if self._row is not None and self._cell is not None:
                self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
            self._in_cell = False
        elif tag == "tr":
            if self._row:
                self._out.append("\n| " + " | ".join(self._row) + " |")
            self._row = None
        elif tag == "table":
            self._out.append("\n")

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_cell and self._cell is not None:
            self._cell.append(text)
        else:
            self._out.append(text if self._in_heading else text + " ")

    def markdown(self) -> str:
        text = "".join(self._out)
        return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n")).strip()


def html_to_markdown(html: str) -> str:
    """Convierte HTML de filing a markdown seccionable (ver docstring)."""
    parser = _SimpleHTMLToMarkdown()
    parser.feed(html)
    return parser.markdown()


def filing_markdown_blocks(html_or_markdown: str, *, is_html: bool = False) -> list[MarkdownBlock]:
    """Entrada HTML o markdown -> bloques con seccion y pagina."""
    markdown = html_to_markdown(html_or_markdown) if is_html else html_or_markdown
    return markdown_blocks(markdown)
