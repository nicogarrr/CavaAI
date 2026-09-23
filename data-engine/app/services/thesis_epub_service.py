"""Conversión de tesis de inversión a EPUB sin dependencias externas.

ebooklib no está disponible en el venv y requirements.txt es de solo lectura,
así que el EPUB se construye a mano con la stdlib: un EPUB es un ZIP con
el `mimetype` sin comprimir en primera posición, `META-INF/container.xml`,
un `content.opf` y capítulos XHTML válidos.

Uso:
    data = ThesisEpubData(ticker="SAN", ...)
    payload: bytes = build_thesis_epub(data)
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

EPUB_MIMETYPE = "application/epub+zip"

DISCLAIMER_ES = (
    "Aviso importante: este documento tiene fines exclusivamente informativos y "
    "educativos. No es asesoramiento de inversión, ni una recomendación de compra "
    "o venta de ningún valor. Toda decisión de inversión conlleva riesgo, incluido "
    "el posible pérdida del capital. Verifica siempre la información con fuentes "
    "primarias antes de actuar."
)

KINDLE_HELP_ES = (
    "Enviar a Kindle: descarga el archivo .epub y envíalo como adjunto desde tu "
    "correo verificado a tu dirección @kindle.com (o súbelo en kindle.amazon.com "
    "con «Enviar a Kindle»). También puedes copiarlo por USB a la carpeta "
    "«documents» de tu Kindle."
)


@dataclass
class EpubSection:
    """Una sección de la tesis (título + cuerpo en texto/markdown ligero)."""

    title: str
    body: str = ""


@dataclass
class ThesisEpubData:
    """Datos mínimos necesarios para renderizar el EPUB de una tesis."""

    ticker: str
    company_name: str = ""
    version: int = 1
    rating: str = "watch"
    status: str = "draft"
    generated_on: str = ""
    executive_summary: str = ""
    sections: list[EpubSection] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)


def slugify(value: str, fallback: str = "seccion") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:48] or fallback


def markdown_lite_to_html(body: str) -> str:
    """Convierte texto con markdown ligero a HTML escapado y seguro.

    Soporta encabezados (#, ##, ###), listas (-, *, 1.) y párrafos.
    Todo el texto se escapa; solo se generan etiquetas propias.
    """
    lines = (body or "").replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    list_ordered = False

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            tag = "ol" if list_ordered else "ul"
            blocks.append(f"<{tag}>" + "".join(f"<li>{item}</li>" for item in list_items) + f"</{tag}>")
            list_items.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_paragraph()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        ordered = re.match(r"^\d+[.)]\s+(.*)$", line)
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1)) + 1  # # -> h2 dentro del capítulo (h1 es el título)
            blocks.append(f"<h{min(level, 4)}>{_inline(heading.group(2))}</h{min(level, 4)}>")
        elif ordered or bullet:
            flush_paragraph()
            is_ordered = ordered is not None
            if list_items and is_ordered != list_ordered:
                flush_list()
            list_ordered = is_ordered
            list_items.append(_inline((ordered or bullet).group(1)))  # type: ignore[union-attr]
        else:
            flush_list()
            paragraph.append(line)
    flush_paragraph()
    flush_list()
    return "\n".join(blocks) if blocks else "<p></p>"


def _inline(text: str) -> str:
    """Escapa HTML y aplica **negrita** inline."""
    escaped = html.escape(text, quote=True)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _chapter(title: str, inner_html: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="es" lang="es">\n'
        "<head><title>" + html.escape(title, quote=True) + "</title>"
        '<link rel="stylesheet" type="text/css" href="style.css"/></head>\n'
        "<body><h1>" + html.escape(title, quote=True) + "</h1>\n" + inner_html + "\n</body>\n</html>\n"
    )


_STYLE_CSS = (
    "body{font-family:Georgia,serif;line-height:1.6;margin:5%;color:#111}"
    "h1{font-size:1.5em;border-bottom:1px solid #999;padding-bottom:.3em}"
    "h2{font-size:1.25em}h3,h4{font-size:1.1em}"
    ".meta{color:#555;font-size:.9em}.disclaimer{background:#fff8e1;border:1px solid #e0c36a;padding:1em}"
    "ul,ol{margin-left:1.2em}"
)

_CONTAINER_XML = (
    '<?xml version="1.0" encoding="utf-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
    "  <rootfiles>\n"
    '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
    "  </rootfiles>\n"
    "</container>\n"
)


def build_thesis_epub(data: ThesisEpubData) -> bytes:
    """Construye un .epub válido a partir de los datos de la tesis."""
    ticker = (data.ticker or "UNKNOWN").upper()
    uid = f"cavaai-thesis-{ticker}-v{data.version}"
    title = f"Tesis de inversión: {ticker}"
    if data.company_name:
        title += f" — {data.company_name}"
    generated = data.generated_on or ""

    chapters: list[tuple[str, str, str]] = []  # (id, filename, xhtml)

    meta_html = (
        f'<p class="meta">Versión {data.version} · rating: {html.escape(data.rating)} · '
        f"estado: {html.escape(data.status)}"
        + (f" · generada el {html.escape(generated)}" if generated else "")
        + "</p>"
    )
    chapters.append(("portada", "portada.xhtml", _chapter(title, meta_html)))

    summary_html = markdown_lite_to_html(data.executive_summary or "Sin resumen ejecutivo disponible.")
    chapters.append(("resumen", "resumen.xhtml", _chapter("Resumen ejecutivo", summary_html)))

    used_slugs: set[str] = set()
    for index, section in enumerate(data.sections, start=1):
        slug = slugify(section.title, fallback=f"seccion-{index}")
        if slug in used_slugs:
            slug = f"{slug}-{index}"
        used_slugs.add(slug)
        filename = f"seccion-{index:02d}-{slug}.xhtml"
        chapters.append(
            (f"sec{index}", filename, _chapter(section.title or f"Sección {index}", markdown_lite_to_html(section.body)))
        )

    if data.citations:
        items = "".join(f"<li>{_inline(cite)}</li>" for cite in data.citations)
        cites_html = f"<ol>{items}</ol>"
    else:
        cites_html = "<p>Sin citas registradas para esta tesis.</p>"
    chapters.append(("citas", "citas.xhtml", _chapter("Citas y evidencia", cites_html)))

    chapters.append(
        ("aviso", "aviso.xhtml", _chapter("Aviso legal", f'<div class="disclaimer"><p>{html.escape(DISCLAIMER_ES)}</p></div>'))
    )

    manifest = ['<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx"/>']
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    manifest.append('<item id="css" href="style.css" media-type="text/css"/>')
    for item_id, filename, _ in chapters:
        manifest.append(f'<item id="{item_id}" href="{html.escape(filename)}" media-type="application/xhtml+xml"/>')
    spine = "".join(f'<itemref idref="{item_id}"/>' for item_id, _, _ in chapters)
    manifest_xml = "\n    ".join(manifest)

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package version="3.0" unique-identifier="uid" xmlns="http://www.idpf.org/2007/opf">\n'
        "  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
        f"    <dc:identifier id=\"uid\">{html.escape(uid)}</dc:identifier>\n"
        f"    <dc:title>{html.escape(title)}</dc:title>\n"
        "    <dc:creator>CavaAI</dc:creator>\n"
        "    <dc:language>es</dc:language>\n"
        + (f"    <dc:date>{html.escape(generated)}</dc:date>\n" if generated else "")
        + "    <meta property=\"dcterms:modified\">2026-01-01T00:00:00Z</meta>\n"
        "  </metadata>\n"
        f"  <manifest>\n    {manifest_xml}\n  </manifest>\n"
        f"  <spine toc=\"ncx\">\n    {spine}\n  </spine>\n"
        "</package>\n"
    )

    nav_items = "".join(
        f'<li><a href="{html.escape(filename)}">{html.escape(_nav_label(filename, data, idx))}</a></li>'
        for idx, (_, filename, _) in enumerate(chapters)
    )
    nav = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="es" lang="es">\n'
        "<head><title>Índice</title></head>\n"
        '<body><nav epub:type="toc"><h1>Índice</h1><ol>' + nav_items + "</ol></nav></body>\n</html>\n"
    )

    ncx_points = "".join(
        f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{html.escape(_nav_label(filename, data, i))}</text>'
        f"</navLabel><content src=\"{html.escape(filename)}\"/></navPoint>"
        for i, (_, filename, _) in enumerate(chapters, start=1)
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        f"<head><meta name=\"dtb:uid\" content=\"{html.escape(uid)}\"/></head>\n"
        f'<docTitle><text>{html.escape(title)}</text></docTitle>\n'
        f"<navMap>{ncx_points}</navMap>\n</ncx>\n"
    )

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zf:
        # El mimetype DEBE ser la primera entrada y SIN comprimir (spec EPUB).
        zf.writestr("mimetype", EPUB_MIMETYPE, compress_type=ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML, compress_type=ZIP_DEFLATED)
        zf.writestr("OEBPS/content.opf", opf, compress_type=ZIP_DEFLATED)
        zf.writestr("OEBPS/toc.ncx", ncx, compress_type=ZIP_DEFLATED)
        zf.writestr("OEBPS/nav.xhtml", nav, compress_type=ZIP_DEFLATED)
        zf.writestr("OEBPS/style.css", _STYLE_CSS, compress_type=ZIP_DEFLATED)
        for _, filename, content in chapters:
            zf.writestr(f"OEBPS/{filename}", content, compress_type=ZIP_DEFLATED)
    return buffer.getvalue()


def _nav_label(filename: str, data: ThesisEpubData, index: int) -> str:
    if filename == "portada.xhtml":
        return "Portada"
    if filename == "resumen.xhtml":
        return "Resumen ejecutivo"
    if filename == "citas.xhtml":
        return "Citas y evidencia"
    if filename == "aviso.xhtml":
        return "Aviso legal"
    section_index = index - 2  # tras portada + resumen
    if 0 <= section_index < len(data.sections):
        return data.sections[section_index].title or f"Sección {section_index + 1}"
    return filename
