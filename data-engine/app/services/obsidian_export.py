"""Exportación Obsidian de tesis persistidas. Solo stdlib, sin almacenamiento."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile


def _yaml(value: str) -> str:
    # JSON strings are a valid YAML scalar and protect frontmatter from injection.
    import json

    return json.dumps(value, ensure_ascii=False)


def _safe_url(url: str | None) -> str:
    if not url:
        return ""
    clean = url.strip()
    if any(character in clean for character in "<>\r\n\t"):
        return ""
    parsed = urlparse(clean)
    return clean if parsed.scheme in {"https", "http"} and parsed.netloc else ""


def _line(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value).strip()


@dataclass
class Source:
    url: str = ""
    date: str = ""
    statement: str = ""
    tier: str = ""


@dataclass
class Note:
    title: str
    version: int = 1
    date: str = ""
    status: str = ""
    body: str = ""
    sources: list[Source] = field(default_factory=list)


def _frontmatter(ticker: str, note: Note) -> str:
    urls = list(dict.fromkeys(url for source in note.sources if (url := _safe_url(source.url))))
    lines = [
        "---",
        f"ticker: {_yaml(ticker)}",
        f"fecha: {_yaml(note.date)}",
        f"estado: {_yaml(note.status)}",
        "fuentes:",
    ]
    lines.extend(f"  - {_yaml(url)}" for url in urls)
    if not urls:
        lines[-1] = "fuentes: []"
    return "\n".join(lines) + "\n---\n\n"


def build_obsidian_zip(ticker: str, notes: list[Note]) -> bytes:
    """Construye notas enlazadas entre sí sin inventar citas ni fechas."""
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,19}", ticker):
        raise ValueError("Ticker inválido")
    if not notes:
        raise ValueError("No hay tesis")
    if len({note.version for note in notes}) != len(notes):
        raise ValueError("Versiones duplicadas")
    output = io.BytesIO()
    folder = f"CavaAI/{ticker}"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        filenames = [f"Tesis {ticker} v{note.version}" for note in notes]
        index_note = Note(title=f"{ticker} - Índice", date=notes[-1].date, status=notes[-1].status)
        index_content = _frontmatter(ticker, index_note) + f"# {ticker} - Índice\n\n## Tesis\n\n"
        index_content += "\n".join(f"- [[{name}]]" for name in reversed(filenames)) + "\n"
        archive.writestr(f"{folder}/{ticker} - Índice.md", index_content)
        for name, note in zip(filenames, notes, strict=True):
            content = _frontmatter(ticker, note) + f"# {note.title}\n\n[[{ticker} - Índice]]\n\n"
            content += (note.body.strip() or "## Sin datos\n\nNo hay contenido de tesis persistido.") + "\n\n"
            content += "## Fuentes\n\n"
            if note.sources:
                for source in note.sources:
                    url = _safe_url(source.url)
                    label = _line(source.statement or source.tier or "Fuente")
                    date = f" ({_line(source.date)})" if source.date else ""
                    # Angle brackets protect Markdown URLs containing parentheses.
                    content += (
                        f"- {label}: [Fuente](<{url}>){date}\n"
                        if url
                        else f"- {label}: Sin datos de URL{date}\n"
                    )
            else:
                content += "Sin datos de fuentes vinculadas.\n"
            content += "\nDocumento informativo de investigación. No es asesoramiento financiero.\n"
            archive.writestr(f"{folder}/{name}.md", content)
    return output.getvalue()
