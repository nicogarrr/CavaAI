"""Verificacion de filings SEC contra su indice oficial antes de ingerirlos.

El operador descarga (desde una red que llega a sec.gov) el indice del filing
y los documentos. Este modulo exige que cada documento quede acreditado por
ese indice y no por lo que declare un manifiesto:

- el indice guardado coincide con su SHA-256 declarado;
- el indice dice CIK, numero de accession, Filing Date, y lista el documento
  con su nombre, tipo y tamano;
- la URL del documento cuelga de /Archives/edgar/data/<CIK>/<accession sin
  guiones>/ y su nombre figura en ese indice;
- el documento servido (sin el envoltorio SGML que sec.gov antepone a los
  exhibits) tiene un tamano coherente con el que el indice declara y su SHA-256
  coincide con el del manifiesto. El tamano NO reconcilia byte a byte: en los
  5 filings de ASTS el servido excede al indice en +2 B (exhibits sin envoltorio)
  o +114 B (iXBRL), causa no identificada. Se acota (MAX_SIZE_DELTA) y la
  diferencia queda registrada en los metadatos; no se presenta como igualdad;
- el CIK del indice es el de la empresa en base de datos.

Nada de esto prueba autoria mas alla de lo que sec.gov sirvio al operador: lo
que se acredita es la coherencia documento <-> indice SEC <-> empresa.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

_SGML_HEAD = re.compile(
    rb"\A<DOCUMENT>\n<TYPE>(?P<type>[^\n]*)\n<SEQUENCE>[^\n]*\n"
    rb"<FILENAME>(?P<name>[^\n]*)\n(?:<DESCRIPTION>[^\n]*\n)?<TEXT>\n"
)
_SGML_TAIL = b"\n</TEXT>\n</DOCUMENT>\n"


MAX_SIZE_DELTA = 256


class EvidenceError(ValueError):
    """El documento no queda acreditado por el indice SEC."""


@dataclass(frozen=True)
class IndexEvidence:
    accession: str
    cik: str
    filing_date: date
    period: date | None
    documents: dict[str, tuple[str, int]]  # filename -> (type, size)


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def parse_index(index_html: str) -> IndexEvidence:
    accession = re.search(r"Accession\s*(?:<[^>]+>\s*)*No\.\s*(?:<[^>]+>\s*)*</strong>\s*(\d{10}-\d{2}-\d{6})", index_html)
    if accession is None:
        accession = re.search(r"(\d{10}-\d{2}-\d{6})", _text(index_html))
    cik = re.search(r"CIK=(\d{10})", index_html)
    filing = re.search(r'Filing Date</div>\s*<div class="info">(\d{4}-\d{2}-\d{2})<', index_html)
    period = re.search(r'Period of Report</div>\s*<div class="info">(\d{4}-\d{2}-\d{2})<', index_html)
    if not (accession and cik and filing):
        raise EvidenceError("Indice SEC ilegible: falta accession, CIK o Filing Date")
    docs: dict[str, tuple[str, int]] = {}
    row = re.compile(
        r'<a href="[^"]*?/([^/"]+\.htm)">[^<]*</a>[^<]*(?:<span[^>]*>[^<]*</span>)?\s*</td>\s*'
        r'<td scope="row">([^<]*)</td>\s*<td scope="row">(\d+)</td>'
    )
    for name, doc_type, size in row.findall(index_html):
        docs[name] = (doc_type.strip(), int(size))
    if not docs:
        raise EvidenceError("Indice SEC sin tabla de documentos")
    return IndexEvidence(
        accession=accession.group(1),
        cik=cik.group(1),
        filing_date=date.fromisoformat(filing.group(1)),
        period=date.fromisoformat(period.group(1)) if period else None,
        documents=docs,
    )


def strip_sgml_wrapper(raw: bytes) -> tuple[bytes, str | None, str | None]:
    """Quita el envoltorio SGML si existe. Devuelve (cuerpo, tipo, nombre); tipo y
    nombre son None cuando el documento no lo trae (p.ej. iXBRL)."""
    head = _SGML_HEAD.match(raw)
    if head is None:
        return raw, None, None
    if not raw.endswith(_SGML_TAIL):
        raise EvidenceError("Envoltorio SGML incompleto")
    body = raw[head.end() : len(raw) - len(_SGML_TAIL)]
    return body, head.group("type").decode(), head.group("name").decode()


@dataclass(frozen=True)
class VerifiedFiling:
    raw: bytes  # bytes servidos por sec.gov: lo que se guarda y lo que cubre sha256
    body: bytes  # raw sin envoltorio SGML: solo para parsear
    body_sha256: str
    sha256: str
    url: str
    filename: str
    form_type: str
    size_delta: int
    filing_date: date
    period: date | None
    accession: str
    cik: str


def _check_capture(entry: dict, base_dir: Path, index: IndexEvidence, filename: str) -> None:
    """Exige la captura hecha por build_sec_evidence con comprobaciones vivas
    contra sec.gov: segunda descarga identica y cruce con data.sec.gov/submissions
    (ticker, CIK, accession, Filing Date y documento principal). Falla cerrado si
    falta: sin captura completa no hay primary_official."""
    import json

    capture = entry.get("capture")
    if not isinstance(capture, dict):
        raise EvidenceError("Falta el bloque capture del builder")
    if capture.get("http_status") != 200 or capture.get("second_fetch_identical") is not True:
        raise EvidenceError("Captura no verificada (estado HTTP o segunda descarga)")
    if capture.get("host") != "www.sec.gov" or not capture.get("fetched_at_utc"):
        raise EvidenceError("Captura sin host sec.gov o sin fecha de descarga")
    sub_bytes = (base_dir / capture["submissions_file"]).read_bytes()
    if hashlib.sha256(sub_bytes).hexdigest() != capture.get("submissions_sha256"):
        raise EvidenceError("submissions guardado no coincide con submissions_sha256")
    sub = json.loads(sub_bytes)
    if str(sub.get("cik", "")).lstrip("0") != index.cik.lstrip("0"):
        raise EvidenceError("submissions de otro CIK")
    recent = sub.get("filings", {}).get("recent", {})
    try:
        position = recent["accessionNumber"].index(index.accession)
    except ValueError as exc:
        raise EvidenceError("submissions no lista ese accession") from exc
    if date.fromisoformat(recent["filingDate"][position]) != index.filing_date:
        raise EvidenceError("Filing Date de submissions distinto del indice")
    if capture.get("is_primary_document") and recent["primaryDocument"][position] != filename:
        raise EvidenceError("El documento no es el principal que dice submissions")


def verify_entry(entry: dict, base_dir: Path, company_cik: str | None) -> VerifiedFiling:
    """Valida una entrada del manifiesto contra el indice SEC guardado."""
    index_bytes = (base_dir / entry["index_file"]).read_bytes()
    if hashlib.sha256(index_bytes).hexdigest() != entry["index_sha256"]:
        raise EvidenceError("El indice guardado no coincide con index_sha256")
    index = parse_index(index_bytes.decode("utf-8", errors="replace"))

    if not company_cik or company_cik.lstrip("0") != index.cik.lstrip("0"):
        raise EvidenceError("El CIK del indice SEC no es el de la empresa")

    parts = urlsplit(entry["url"])
    if parts.scheme != "https" or parts.hostname != "www.sec.gov":
        raise EvidenceError("La URL del documento no es https://www.sec.gov")
    segments = parts.path.strip("/").split("/")
    if (
        len(segments) != 6
        or segments[:3] != ["Archives", "edgar", "data"]
        or segments[3].lstrip("0") != index.cik.lstrip("0")
        or segments[4] != index.accession.replace("-", "")
    ):
        raise EvidenceError("La URL no cuelga del CIK/accession del indice")
    filename = segments[5]
    if filename not in index.documents:
        raise EvidenceError("El indice SEC no lista ese documento")
    index_type, index_size = index.documents[filename]

    raw = (base_dir / entry["file"]).read_bytes()
    body, sgml_type, sgml_name = strip_sgml_wrapper(raw)
    if sgml_name is not None and (sgml_name != filename or sgml_type != index_type):
        raise EvidenceError("Nombre o tipo del documento no coinciden con el indice")
    size_delta = len(body) - index_size
    if abs(size_delta) > MAX_SIZE_DELTA:
        raise EvidenceError(f"Tamano {len(body)} incoherente con el indice SEC ({index_size})")
    sha = hashlib.sha256(raw).hexdigest()
    if sha != entry["sha256"]:
        raise EvidenceError("sha256 de los bytes servidos distinto del manifiesto")
    _check_capture(entry, base_dir, index, filename)
    return VerifiedFiling(
        raw=raw,
        body=body,
        body_sha256=hashlib.sha256(body).hexdigest(),
        sha256=sha,
        url=entry["url"],
        filename=filename,
        form_type=index_type,
        size_delta=size_delta,
        filing_date=index.filing_date,
        period=index.period,
        accession=index.accession,
        cik=index.cik,
    )
