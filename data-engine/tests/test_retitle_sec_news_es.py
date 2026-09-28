"""Script de saneado de titulares SEC: lógica pura + end-to-end con BD."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal, init_db
from app.models import Company, NewsEvent
from scripts.retitle_sec_news_es import (
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


def test_plan_row():
    row = SimpleNamespace(
        id=1, tenant_id=None, title="COST COST 8-K (2026-09-24)",
        summary="COST COST 8-K (2026-09-24)",
        metadata_={"source_headline": "COST 8-K (2026-09-24)"},
    )
    plan = _plan_row(row, "COST")
    assert plan["new"]["title"] == "COST 8-K presentado ante la SEC"
    assert plan["new"]["source_headline"] == "8-K presentado ante la SEC"  # sin prefijo
    assert plan["expected"]["title"] == "COST COST 8-K (2026-09-24)"
    row_es = SimpleNamespace(
        id=2, tenant_id=None, title="COST 8-K presentado ante la SEC",
        summary="COST 8-K presentado ante la SEC",
        metadata_={"source_headline": "8-K presentado ante la SEC"},
    )
    assert _plan_row(row_es, "COST") is None  # ya saneada: no se toca
    row_otro = SimpleNamespace(
        id=3, tenant_id=None, title="Apple anuncia resultados",
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


def test_dry_run_no_escribe(db_rows, tmp_path, capsys):
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
    assert "candidatas SEC estrictas" in out and ": 0" in out.split("candidatas SEC estrictas")[1].splitlines()[0]


def test_apply_sanea_los_tres_campos_y_backup_durable(db_rows, tmp_path):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    assert main(["--plan", str(plan)]) == 0
    backup = tmp_path / "backup.json"
    assert main(["--apply", "--plan", str(plan), "--backup", str(backup)]) == 0
    db.expire_all()
    row = db.get(NewsEvent, row.id)
    assert row.title == "SEEDC 8-K presentado ante la SEC"
    assert row.summary == "SEEDC 8-K presentado ante la SEC"
    assert row.metadata_["source_headline"] == "8-K presentado ante la SEC"
    # Los originales quedan preservados (nunca se finge reescribir el histórico).
    assert row.metadata_["sec_sanitize"]["original"]["title"] == "SEEDC SEEDC 8-K (2026-09-24)"
    payload = json.loads(backup.read_text(encoding="utf-8"))
    assert payload[0]["old"]["title"] == "SEEDC SEEDC 8-K (2026-09-24)"
    # Backup exclusivo: un segundo apply con la misma ruta falla ANTES de tocar BD.
    with pytest.raises(FileExistsError):
        main(["--apply", "--plan", str(plan), "--backup", str(backup)])


def test_apply_salta_filas_cambiadas_desde_el_plan(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])  # dry-run: plan revisado
    db.get(NewsEvent, row.id).title = "Editado por otra persona (2026-09-24)"
    db.commit()
    assert main(["--apply", "--plan", str(plan), "--backup", str(tmp_path / "b.json")]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "Editado por otra persona (2026-09-24)"
    assert "saltadas por cambio de estado" in capsys.readouterr().out


def test_colision_se_salta_y_reporta(db_rows, tmp_path, capsys):
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


def test_rollback_con_precondicion(db_rows, tmp_path, capsys):
    db, company = db_rows
    row = _add_sec_row(db, company, "SEEDC 8-K (2026-09-24)", "SEEDC 8-K (2026-09-24)")
    plan = tmp_path / "plan.json"
    main(["--plan", str(plan)])
    backup = tmp_path / "b.json"
    main(["--apply", "--plan", str(plan), "--backup", str(backup)])
    # Rollback en dry-run: preview sin escrituras.
    assert main(["--rollback", str(backup)]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "SEEDC 8-K presentado ante la SEC"
    assert "DRY-RUN" in capsys.readouterr().out
    # Una edición posterior bloquea la reversión de ESA fila.
    db.get(NewsEvent, row.id).title = "Edición posterior"
    db.commit()
    assert main(["--rollback", str(backup), "--apply"]) == 0
    db.expire_all()
    assert db.get(NewsEvent, row.id).title == "Edición posterior"
    out = capsys.readouterr().out
    assert "saltadas" in out
