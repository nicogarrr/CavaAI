"""Script de saneado de titulares SEC: lógica pura + end-to-end con BD."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models import Company, NewsEvent
from scripts.retitle_sec_news_es import (
    _apply_plan,
    _english_pattern,
    _form_from,
    _is_sec_url,
    _plan_row,
    _strip_ticker_prefixes,
    main,
)

SEC_URL = "https://www.sec.gov/Archives/edgar/data/1000000/0000950000000001/x.htm"


# ---------- lógica pura ----------

def test_patron_ingles_estricto():
    assert _english_pattern("COST 8-K (2026-09-24)")
    assert _english_pattern("8-K filed 2026-09-24")
    assert not _english_pattern("COST 8-K presentado ante la SEC")
    assert not _english_pattern("Apple anuncia resultados")


def test_url_sec_estricta():
    assert _is_sec_url(SEC_URL)
    assert _is_sec_url("https://data.sec.gov/Archives/edgar/data/1/x")
    assert not _is_sec_url("https://sec.gov.attacker.example/Archives/edgar/data/1/x")
    assert not _is_sec_url("http://www.sec.gov/Archives/edgar/data/1/x")  # exige https
    assert not _is_sec_url("https://www.sec.gov/otra/ruta")
    assert not _is_sec_url("https://example.com/Archives/edgar/data/1/x")
    assert not _is_sec_url(None)


def test_quita_doble_prefijo_de_ticker():
    assert _strip_ticker_prefixes("COST COST 8-K (2026-09-24)", "COST") == "8-K (2026-09-24)"
    assert _strip_ticker_prefixes("COSTCO sube", "COST") == "COSTCO sube"


def test_form_allowlist():
    assert _form_from("COST 8-K (2026-09-24)", "COST") == "8-K"
    assert _form_from("10-K/A filed 2026-01-01", "") == "10-K/A"
    assert _form_from("XYZ-9 weird (2026-09-24)", "") is None  # no inventa forms


def test_plan_row_solo_texto_compuesto():
    row = SimpleNamespace(
        id=1, tenant_id=None, company_id=7, title="COST COST 8-K (2026-09-24)",
        summary="COST COST 8-K (2026-09-24)",
        metadata_={"source_headline": "COST 8-K (2026-09-24)"},
    )
    plan = _plan_row(row, "COST")
    assert plan["new"] == {
        "title": "COST 8-K presentado ante la SEC",
        "summary": "COST 8-K presentado ante la SEC",
        "source_headline": None,
        "headline_from_source": False,
    }
    # Procedencia histórica: el plan RETIRA el titular sintético atribuido a
    # la SEC (guardado en expected para rollback) y marca el display como
    # generado por CavaAI.
    assert plan["expected"]["source_headline"] == "COST 8-K (2026-09-24)"
    assert plan["new"]["source_headline"] is None
    assert plan["new"]["headline_from_source"] is False
    # Fila con texto ya saneado pero titular sintético aún atribuido a la
    # SEC: el plan sanea SOLO la procedencia (title/summary quedan igual).
    row_es = SimpleNamespace(
        id=2, tenant_id=None, company_id=7, title="COST 8-K presentado ante la SEC",
        summary="COST 8-K presentado ante la SEC",
        metadata_={"source_headline": "8-K presentado ante la SEC"},
    )
    plan_es = _plan_row(row_es, "COST")
    assert plan_es is not None
    assert plan_es["new"]["title"] == row_es.title
    assert plan_es["new"]["source_headline"] is None
    assert plan_es["new"]["headline_from_source"] is False
    # Y la fila ya saneada por completo (texto y procedencia) no se toca.
    row_ok = SimpleNamespace(
        id=3, tenant_id=None, company_id=7, title="COST 8-K presentado ante la SEC",
        summary="COST 8-K presentado ante la SEC",
        metadata_={"headline_from_source": False},
    )
    assert _plan_row(row_ok, "COST") is None
    row_otro = SimpleNamespace(
        id=3, tenant_id=None, company_id=7, title="Apple anuncia resultados",
        summary="Apple anuncia resultados", metadata_={},
    )
    assert _plan_row(row_otro, "AAPL") is None


# ---------- end-to-end con BD ----------

@pytest.fixture
def db_rows():
    init_db()
    db = SessionLocal()
    for stale in db.scalars(select(NewsEvent)).all():
        db.delete(stale)
    company = db.scalar(select(Company).where(Company.ticker == "SEEDC"))
    if company is None:
        db.add(Company(
            ticker="SEEDC", name="Seed Co", exchange="NASDAQ", currency="USD",
            sector="Technology", industry="Software", company_type="tech",
            valuation_model="standard_dcf", special_sources=[], special_risks=[], factor_tags=[],
        ))
        db.commit()
        company = db.scalar(select(Company).where(Company.ticker == "SEEDC"))
    yield db, company
    db.close()


def _add_sec_row(db, company, title, headline, url=SEC_URL, source="SEC", summary=None):
    row = NewsEvent(
        company_id=company.id if company else None,
        title=title,
        summary=summary if summary is not None else title,
        source=source,
        url=url,
        metadata_={"connector": "sec", "source_headline": headline},
    )
    db.add(row)
    db.commit()
    return row


def _plan_and_apply(tmp_path):
    plan = tmp_path / "plan.json"
    backup = tmp_path / "backup.json"
    assert main(["--plan", str(plan)]) == 0
    assert main(["--apply", "--plan", str(plan), "--backup", str(backup)]) == 0
    return backup


def test_dry_run_no_escribe(db_rows, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    assert main([]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "SEEDC 8-K (2026-09-24)"
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "a sanear: 1" in out


def test_match_estricto_descarta_falsos_positivos(db_rows, capsys):
    db, company = db_rows
    _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)",
                 url="https://sec.gov.attacker.example/Archives/edgar/data/1/x")
    _add_sec_row(db, company, "SEEDC 10-Q (2026-06-30)", "SEEDC 10-Q (2026-06-30)",
                 url="http://www.sec.gov/Archives/edgar/data/1/x")
    _add_sec_row(db, company, "SEEDC S-1 (2026-01-15)", "SEEDC S-1 (2026-01-15)", source="manual")
    assert main([]) == 0
    out = capsys.readouterr().out
    line = [l for l in out.splitlines() if "candidatas SEC estrictas" in l][0]
    assert line.endswith(": 0")


def test_apply_sanea_texto_compuesto_y_retira_procedencia_historica(db_rows, tmp_path):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    backup = _plan_and_apply(tmp_path)
    db.expire_all()
    row = db.get(NewsEvent, row.id)
    assert row.title == "SEEDC 8-K presentado ante la SEC"
    assert row.summary == "SEEDC 8-K presentado ante la SEC"
    # El titular sintético («SEEDC 8-K (fecha)») NO era un titular publicado
    # por la SEC: se retira de la metadata para que ningún lector de #574 lo
    # siga atribuyendo a la fuente, y el flag marca el display como nuestro.
    assert "source_headline" not in row.metadata_
    assert row.metadata_["headline_from_source"] is False
    assert "sec_sanitize" not in row.metadata_
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload[0]["old"]["title"] == "SEEDC SEEDC 8-K (2026-09-24)"
    assert payload[0]["old"]["source_headline"] == "SEEDC 8-K (2026-09-24)"
    assert payload[0]["new"]["summary"] == "SEEDC 8-K presentado ante la SEC"
    # Backup exclusivo: un segundo apply con la misma ruta falla ANTES de tocar BD.
    with pytest.raises(FileExistsError):
        main(["--apply", "--plan", str(tmp_path / "plan.json"), "--backup", str(backup)])


def test_fila_historica_deja_de_alimentar_al_lector_de_titulares(db_rows, tmp_path):
    """E2E: una fila SEC histórica con titular sintético deja de ser elegible
    para el lector de #574 (tracked_news_alerts exige source_headline), mientras
    una fila con titular verbatim REAL de la fuente sigue siéndolo."""
    from sqlalchemy import select

    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    verbatim = _add_sec_row(
        db,
        company,
        "SeedCube presenta su informe anual",
        "SeedCube Files Annual Report, Outlines Growth Plans",
        url="https://www.sec.gov/Archives/edgar/data/9999999999/000999999926000001/",
    )
    eligible = select(NewsEvent).where(
        NewsEvent.source == "SEC",
        NewsEvent.metadata_["source_headline"].as_string().isnot(None),
    )
    assert {r.id for r in db.scalars(eligible)} == {row.id, verbatim.id}
    _plan_and_apply(tmp_path)
    db.expire_all()
    # Tras el saneado: la fila histórica ya no alimenta al lector; la fila
    # con titular verbatim no era candidata (título ya en español) y queda.
    remaining = {r.id for r in db.scalars(eligible)}
    assert row.id not in remaining
    assert verbatim.id in remaining
    assert db.get(NewsEvent, row.id).metadata_["headline_from_source"] is False


def test_apply_salta_filas_cambiadas_desde_el_plan(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    db.get(NewsEvent, row.id).summary = "Resumen editado por otra persona"
    db.commit()
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    row = db.get(NewsEvent, row.id)
    assert row.title == "SEEDC 8-K (2026-09-24)"
    assert row.summary == "Resumen editado por otra persona"
    assert "saltadas al aplicar por revalidación" in capsys.readouterr().out


def test_apply_revalida_origen_al_aplicar(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    # La fila deja de ser SEC entre la revisión del plan y el apply.
    stale = db.get(NewsEvent, row.id)
    stale.source = "manual"
    db.commit()
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "SEEDC 8-K (2026-09-24)"
    assert "saltadas al aplicar por revalidación" in capsys.readouterr().out


def test_colision_en_bd_se_salta(db_rows, tmp_path, capsys):
    db, company = db_rows
    _add_sec_row(db, company, "SEEDC 8-K presentado ante la SEC", "8-K presentado ante la SEC",
                 url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000002/y.htm")
    vieja = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    assert db.get(NewsEvent, vieja.id).title == "SEEDC 8-K (2026-09-24)"  # intacta
    assert "COLISIÓN" in capsys.readouterr().out


def test_colision_intraplan_se_detecta(db_rows, tmp_path, capsys):
    db, company = db_rows
    # Dos filas EN distintas que convergen al mismo título destino.
    _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)",
                 url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000001/a.htm")
    _add_sec_row(db, company, "SEEDC SEEDC 8-K (2026-09-24)", "SEEDC SEEDC 8-K (2026-09-24)",
                 url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000001/b.htm")
    plan = tmp_path / "plan.json"
    assert main(["--plan", str(plan)]) == 0
    out = capsys.readouterr().out
    assert "COLISIÓN" in out
    planned = json.loads(plan.read_text(encoding="utf-8"))
    assert len(planned) == 1  # solo una entra al plan; la otra se reporta


def test_rollback_con_precondicion_en_ambos_campos(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    backup = _plan_and_apply(tmp_path)
    # Rollback en dry-run: preview sin escrituras.
    assert main(["--rollback", str(backup)]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "SEEDC 8-K presentado ante la SEC"
    assert "DRY-RUN" in capsys.readouterr().out
    # Rollback real restaura title y summary.
    assert main(["--rollback", str(backup), "--apply"]) == 0
    db.expire_all()
    row = db.get(NewsEvent, row.id)
    assert row.title == "SEEDC 8-K (2026-09-24)"
    assert row.summary == "SEEDC 8-K (2026-09-24)"
    # Y la procedencia vuelve a su estado previo (para que el rollback sea
    # una reversión real de este plan, incluida la metadata).
    assert row.metadata_["source_headline"] == "SEEDC 8-K (2026-09-24)"
    assert "headline_from_source" not in row.metadata_
    # Una edición posterior SOLO en summary también bloquea la reversión.
    main(["--apply", "--plan", str(tmp_path / "plan.json"), "--backup", str(tmp_path / "b2.json")])
    db.get(NewsEvent, row.id).summary = "editado después"
    db.commit()
    assert main(["--rollback", str(tmp_path / "b2.json"), "--apply"]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).summary == "editado después"
    assert "saltadas" in capsys.readouterr().out


def test_apply_salta_si_company_cambia_tras_el_plan(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    otra = db.scalar(select(Company).where(Company.ticker == "SEED2"))
    if otra is None:
        otra = Company(
            ticker="SEED2", name="Seed Two", exchange="NASDAQ", currency="USD",
            sector="Technology", industry="Software", company_type="tech",
            valuation_model="standard_dcf", special_sources=[], special_risks=[], factor_tags=[],
        )
        db.add(otra)
        db.commit()
    stale = db.get(NewsEvent, row.id)
    stale.company_id = otra.id
    db.commit()
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    row = db.get(NewsEvent, row.id)
    # Identidad ambigua: no se toca la fila.
    assert row.title == "SEEDC 8-K (2026-09-24)"
    assert row.company_id == otra.id
    assert "saltadas al aplicar por revalidación" in capsys.readouterr().out


def test_colision_aparecida_tras_el_plan_se_salta(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    # Entre la revisión del plan y el apply llega una fila nueva con el
    # título destino (sin UNIQUE constraint, el duplicado entraría mudo).
    _add_sec_row(db, company, "SEEDC 8-K presentado ante la SEC", "8-K presentado ante la SEC",
                 url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000003/z.htm")
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "SEEDC 8-K (2026-09-24)"  # intacta
    assert "saltadas al aplicar por revalidación" in capsys.readouterr().out


def test_apply_plan_intraplan_mismo_destino_salta_la_segunda(db_rows):
    db, company = db_rows
    a = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)",
                     url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000001/a.htm")
    b = _add_sec_row(db, company, "SEEDC SEEDC 8-K (2026-09-24)", "SEEDC SEEDC 8-K (2026-09-24)",
                     url="https://www.sec.gov/Archives/edgar/data/1000000/0000950000000001/b.htm")

    def _entry(r):
        return {
            "id": r.id, "tenant_id": r.tenant_id, "company_id": r.company_id,
            "expected": {"title": r.title, "summary": r.summary,
                         "source_headline": r.metadata_["source_headline"]},
            "new": {"title": "SEEDC 8-K presentado ante la SEC",
                    "summary": "SEEDC 8-K presentado ante la SEC"},
        }

    applied, skipped = _apply_plan(db, [_entry(a), _entry(b)])
    db.commit()
    assert applied == 1
    assert skipped == [b.id]
    db.expire_all()
    assert db.get(NewsEvent, a.id).title == "SEEDC 8-K presentado ante la SEC"
    assert db.get(NewsEvent, b.id).title == "SEEDC SEEDC 8-K (2026-09-24)"
