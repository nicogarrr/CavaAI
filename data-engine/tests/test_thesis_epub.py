"""Tests herméticos de exportación de tesis a EPUB.

Sin red y sin ebooklib: el EPUB se construye con la stdlib (ZIP) y aquí se
valida la estructura (mimetype primero y sin comprimir, container, OPF,
nº de capítulos) tanto a nivel de servicio como del endpoint
GET /api/thesis/{ticker}/epub (200 descarga / 404 limpio sin tesis).

Run from data-engine/:
    pytest tests/test_thesis_epub.py -v
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import main
from app.core.database import Base, get_db
from app.models import Claim, Company, Tenant, ThesisSection, ThesisVersion
from app.services.thesis_epub_service import (
    DISCLAIMER_ES,
    EPUB_MIMETYPE,
    EpubSection,
    ThesisEpubData,
    build_thesis_epub,
)


def _sample_data() -> ThesisEpubData:
    return ThesisEpubData(
        ticker="SAN",
        company_name="Banco Santander",
        version=2,
        rating="buy",
        status="final",
        generated_on="2026-09-21",
        executive_summary="Resumen **sólido** del banco.\n\nSegundo párrafo.",
        sections=[
            EpubSection(title="Valoración", body="# Rango\n\n- Toro: 8€\n- Base: 6€"),
            EpubSection(title="Riesgos", body="Riesgo de tipos y **mora**."),
        ],
        citations=["[verified] El margen crece (https://ejemplo.com/fuente)"],
    )


def _open_epub(payload: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(payload))


def test_build_epub_es_zip_valido_con_mimetype_primero():
    payload = build_thesis_epub(_sample_data())
    assert payload[:2] == b"PK"

    with _open_epub(payload) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype", f"mimetype debe ser la primera entrada: {names[:3]}"
        info = zf.getinfo("mimetype")
        assert info.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype").decode("ascii") == EPUB_MIMETYPE
        assert "META-INF/container.xml" in names
        assert "OEBPS/content.opf" in names


def test_build_epub_numero_de_capitulos_y_contenido():
    data = _sample_data()
    with _open_epub(build_thesis_epub(data)) as zf:
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        spine_refs = [i.get("idref") for i in opf.findall("./opf:spine/opf:itemref", ns)]
        # portada + resumen + 2 secciones + citas + aviso
        assert spine_refs == ["portada", "resumen", "sec1", "sec2", "citas", "aviso"]

        manifest = {i.get("id"): i.get("href") for i in opf.findall("./opf:manifest/opf:item", ns)}
        for ref in spine_refs:
            assert ref in manifest, f"capítulo {ref} sin entrada en manifest"

        aviso = zf.read("OEBPS/aviso.xhtml").decode("utf-8")
        assert "asesoramiento" in aviso
        assert DISCLAIMER_ES.split(".")[0][:40] in aviso

        citas = zf.read("OEBPS/citas.xhtml").decode("utf-8")
        assert "margen crece" in citas

        resumen = zf.read("OEBPS/resumen.xhtml").decode("utf-8")
        assert "<strong>sólido</strong>" in resumen

        container = zf.read("META-INF/container.xml").decode("utf-8")
        assert "OEBPS/content.opf" in container


def test_build_epub_escapa_html_inyectado():
    data = _sample_data()
    data.sections = [EpubSection(title="<script>alert(1)</script>", body="<img src=x onerror=y>")]
    with _open_epub(build_thesis_epub(data)) as zf:
        chapter = zf.read("OEBPS/seccion-01-script-alert-1-script.xhtml").decode("utf-8")
        assert "<script>" not in chapter
        assert "&lt;script&gt;" in chapter
        assert "<img" not in chapter


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    tenant = Tenant(external_id="epub-test", name="EPUB Test")
    session.add(tenant)
    session.flush()
    session.info["tenant_id"] = tenant.id

    company = Company(
        ticker="SAN",
        name="Banco Santander",
        exchange="BME",
        currency="EUR",
        sector="Financials",
        industry="Banks",
        company_type="standard",
        valuation_model="standard_dcf",
        special_sources=[],
        special_risks=[],
        factor_tags=[],
    )
    session.add(company)
    session.flush()

    thesis = ThesisVersion(
        company_id=company.id,
        version=3,
        status="final",
        thesis_markdown="# Tesis SAN",
        executive_summary="Resumen ejecutivo de prueba.",
        rating="buy",
    )
    session.add(thesis)
    session.flush()

    session.add(
        ThesisSection(
            thesis_version_id=thesis.id,
            company_id=company.id,
            section_key="valuation",
            title="Valoración",
            body="Base: 6€.",
            status="published",
            order_index=1,
        )
    )
    session.add(
        Claim(
            company_id=company.id,
            thesis_version_id=thesis.id,
            statement="El margen de intereses crece.",
            status="verified",
            materiality_score=8,
        )
    )
    session.commit()

    def _override():
        yield session

    main.app.dependency_overrides[get_db] = _override
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_epub_endpoint_devuelve_descarga_valida(client):
    response = client.get("/api/thesis/SAN/epub")
    assert response.status_code == 200, response.text[:300]
    assert response.headers["content-type"] == "application/epub+zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "cavaai-thesis-SAN-v3.epub" in response.headers["content-disposition"]

    with _open_epub(response.content) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"
        assert zf.read("mimetype").decode("ascii") == EPUB_MIMETYPE
        opf = ET.fromstring(zf.read("OEBPS/content.opf"))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        spine_refs = [i.get("idref") for i in opf.findall("./opf:spine/opf:itemref", ns)]
        # portada + resumen + 1 sección + citas + aviso
        assert spine_refs == ["portada", "resumen", "sec1", "citas", "aviso"]
        citas = zf.read("OEBPS/citas.xhtml").decode("utf-8")
        assert "margen de intereses" in citas


def test_epub_endpoint_404_limpio_sin_tesis(client):
    response = client.get("/api/thesis/NADAAAA/epub")
    assert response.status_code == 404
    assert response.json() == {"detail": "No thesis for ticker"}
