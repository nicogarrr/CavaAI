"""Tests adversariales del anclaje de datos a la frase exacta del filing.

Regla de la casa: un dato sin ancla verificable no se publica; OFICIAL exige
el valor literal en la cita; INFERIDO exige derivacion trazable; la ausencia
nunca se representa como 0 ni como cadena vacia.
"""

import pytest
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import Session

from app.models.entities import Company, FactAnchor, Tenant
from app.services.fact_anchor import (
    FactAnchorError,
    FactAnchorSpec,
    build_anchor,
    item_for_offset,
    locate_quote,
    locate_unique,
    sha256_text,
    verify_anchor,
)

BODY = (
    "Item 1.01. Entry into a Material Definitive Agreement.\n"
    "On September 29, 2026, Acme Corp entered into an Agreement and Plan of Merger "
    "with Beta Inc. Under the terms of the Agreement, holders of Beta common stock "
    "will receive $54.20 in cash for each share of Beta common stock.\n"
    "Item 9.01. Financial Statements and Exhibits.\n"
    "(d) Exhibits. Exhibit 2.1 Agreement and Plan of Merger.\n"
)

QUOTE = "will receive $54.20 in cash for each share of Beta common stock."


def _build(**over):
    args = dict(
        body=BODY,
        accession="0001193125-26-004321",
        filename="d123456d8k.htm",
        field="offer_price",
        value_text="$54.20",
        label="OFICIAL",
        quote=QUOTE,
        extractor="instinct/test-1.0",
    )
    args.update(over)
    return build_anchor(**args)


class TestLocateQuote:
    def test_cita_unica_devuelve_su_desplazamiento_exacto(self):
        quote = "will receive $54.20 in cash"
        (offset,) = locate_quote(BODY, quote)
        assert BODY[offset : offset + len(quote)] == quote

    def test_cita_ausente_devuelve_lista_vacia_no_cero(self):
        assert locate_quote(BODY, "no estoy en el documento") == []

    def test_cita_vacia_es_error_nunca_offset_cero(self):
        with pytest.raises(FactAnchorError):
            locate_quote(BODY, "")

    def test_cita_duplicada_devuelve_todos_los_offsets(self):
        assert locate_quote(BODY, "Beta common stock") == [
            BODY.find("Beta common stock"),
            BODY.rfind("Beta common stock"),
        ]

    def test_locate_unique_rechaza_duplicados_en_vez_de_elegir_en_silencio(self):
        with pytest.raises(FactAnchorError, match="2 veces"):
            locate_unique(BODY, "Beta common stock")

    def test_locate_unique_rechaza_cita_ausente(self):
        with pytest.raises(FactAnchorError, match="no aparece"):
            locate_unique(BODY, "texto que no existe")

    def test_unicode_y_acentos_son_literales(self):
        body = "El acuerdo incluirá una indemnización de 12,5 millones de euros."
        quote = "indemnización de 12,5 millones"
        (offset,) = locate_quote(body, quote)
        assert body[offset : offset + len(quote)] == quote


class TestItemForOffset:
    def test_devuelve_el_item_que_precede_a_la_cita(self):
        offset = BODY.find("$54.20")
        assert item_for_offset(BODY, offset) == "Item 1.01"

    def test_sin_item_previo_devuelve_none_no_inventa(self):
        assert item_for_offset("texto sin items", 3) is None

    def test_un_item_posterior_no_cuenta(self):
        offset = BODY.find("Item 1.01")
        assert item_for_offset(BODY, offset) is None

    def test_offset_fuera_de_rango_es_error(self):
        with pytest.raises(FactAnchorError):
            item_for_offset(BODY, len(BODY) + 1)


class TestBuildAnchor:
    def test_construye_sha_y_offset_sin_que_el_caller_los_pueda_falsear(self):
        anchor = _build()
        assert anchor.body_sha256 == sha256_text(BODY)
        assert BODY[anchor.quote_offset :].startswith(anchor.quote)
        assert anchor.item == "Item 1.01"

    def test_etiqueta_desconocida_es_error(self):
        with pytest.raises(FactAnchorError, match="Etiqueta"):
            _build(label="MAS_O_MENOS_OFICIAL")

    def test_valor_vacio_es_error_la_ausencia_nunca_es_cadena_vacia(self):
        with pytest.raises(FactAnchorError, match="valor"):
            _build(value_text="   ")

    def test_campo_vacio_es_error(self):
        with pytest.raises(FactAnchorError):
            _build(field=" ")

    @pytest.mark.parametrize("campo", ["accession", "filename", "extractor"])
    def test_identidad_vacia_es_error(self, campo):
        with pytest.raises(FactAnchorError):
            _build(**{campo: "  "})

    def test_cita_que_no_esta_en_el_documento_no_ancla(self):
        with pytest.raises(FactAnchorError):
            _build(quote="will receive $99.99 in cash")

    def test_oficial_exige_valor_literal_en_la_cita(self):
        with pytest.raises(FactAnchorError, match="literal"):
            _build(value_text="$99.99")

    def test_oficial_rechaza_normalizacion_no_literal(self):
        # "54,20 EUR" no aparece literal en la cita: no es OFICIAL.
        with pytest.raises(FactAnchorError, match="INFERIDO"):
            _build(value_text="54,20 EUR")

    def test_inferido_exige_derivacion_trazable(self):
        with pytest.raises(FactAnchorError, match="derivation"):
            _build(label="INFERIDO", value_text="54.20")

    def test_inferido_con_derivacion_es_valido(self):
        anchor = _build(
            label="INFERIDO",
            value_text="54.20",
            derivation="strip del signo $ sobre la cita anclada",
        )
        assert anchor.label == "INFERIDO"
        assert anchor.derivation

    def test_item_declarado_que_contradice_la_estructura_es_error(self):
        with pytest.raises(FactAnchorError, match="contradice"):
            _build(item="Item 8.01")

    def test_item_declarado_coherente_es_aceptado(self):
        assert _build(item="Item 1.01").item == "Item 1.01"


class TestVerifyAnchor:
    def test_ancla_valida_verifica(self):
        assert verify_anchor(BODY, _build()) is True

    def _tampered(self, **over):
        anchor = _build()
        return FactAnchorSpec(**{**anchor.__dict__, **over})

    def test_documento_distinto_no_verifica_por_sha(self):
        assert verify_anchor(BODY + " ", _build()) is False

    def test_offset_manipulado_no_verifica(self):
        anchor = self._tampered(quote_offset=_build().quote_offset - 1)
        assert verify_anchor(BODY, anchor) is False

    def test_cita_manipulada_no_verifica(self):
        anchor = self._tampered(quote=QUOTE.replace("54.20", "54.21"))
        assert verify_anchor(BODY, anchor) is False

    def test_valor_manipulado_no_verifica_aunque_la_cita_sea_real(self):
        anchor = self._tampered(value_text="$99.99")
        assert verify_anchor(BODY, anchor) is False

    def test_etiqueta_invalida_no_verifica(self):
        assert verify_anchor(BODY, self._tampered(label="MAS_O_MENOS")) is False

    def test_cita_vacia_no_verifica(self):
        assert verify_anchor(BODY, self._tampered(quote="", quote_offset=-1)) is False

    def test_item_inventado_no_verifica(self):
        assert verify_anchor(BODY, self._tampered(item="Item 8.01")) is False

    def test_cita_duplicada_en_el_documento_no_verifica(self):
        body = BODY + "\n" + QUOTE + "\n"
        # El sha ya no coincide: reconstruimos el spec con el sha del body nuevo.
        anchor = self._tampered(body_sha256=sha256_text(body))
        assert verify_anchor(body, anchor) is False

    def test_inferido_sin_derivacion_no_verifica(self):
        anchor = _build(label="INFERIDO", value_text="54.20", derivation="strip $")
        assert verify_anchor(BODY, self._tampered(label="INFERIDO", derivation=None)) is False
        assert verify_anchor(BODY, anchor) is True


class TestFactAnchorModel:
    def test_unicidad_incluye_tenant_y_version_del_documento(self):
        constraints = [
            c for c in FactAnchor.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert any(
            [col.name for col in c.columns]
            == ["tenant_id", "accession_number", "filename", "field", "quote_offset", "body_sha256"]
            for c in constraints
        )

    def test_tenant_id_indexado(self):
        assert FactAnchor.__table__.c.tenant_id.index is True

    @pytest.fixture()
    def session(self):
        engine = create_engine("sqlite:///:memory:")
        Tenant.__table__.create(engine)
        Company.__table__.create(engine)
        FactAnchor.__table__.create(engine)
        with Session(engine) as s:
            yield s

    def _row(self, session):
        row = FactAnchor.from_spec(_build(), body=BODY, tenant_id=None)
        session.add(row)
        session.commit()
        return row

    def test_from_spec_rechaza_spec_manipulado_al_persistir(self, session):
        from dataclasses import replace

        spec = replace(_build(), value_text="$99.99")
        with pytest.raises(FactAnchorError):
            FactAnchor.from_spec(spec, body=BODY, tenant_id=None)

    def test_constructor_directo_cerrado(self):
        with pytest.raises(FactAnchorError):
            FactAnchor(tenant_id=None, accession_number="x", value_text="$1")

    def test_bulk_update_orm_bloqueado(self, session):
        self._row(session)
        with pytest.raises(FactAnchorError):
            session.execute(
                update(FactAnchor)
                .where(FactAnchor.accession_number == "0001193125-26-004321")
                .values(value_text="$99.99")
            )
        session.rollback()

    def test_bulk_delete_orm_bloqueado(self, session):
        self._row(session)
        with pytest.raises(FactAnchorError):
            session.execute(
                delete(FactAnchor).where(
                    FactAnchor.accession_number == "0001193125-26-004321"
                )
            )
        session.rollback()

    def test_mutacion_pre_insert_no_persiste(self, session):
        row = FactAnchor.from_spec(_build(), body=BODY, tenant_id=None)
        row.value_text = "$99.99"
        session.add(row)
        with pytest.raises(FactAnchorError):
            session.commit()
        session.rollback()

    def test_mutacion_pre_insert_de_quote_hash_label_item_no_persiste(self, session):
        for field, value in (
            ("quote", "texto inventado"),
            ("body_sha256", "0" * 64),
            ("label", "INFERIDO"),
            ("item", "Item 9.99"),
        ):
            row = FactAnchor.from_spec(_build(), body=BODY, tenant_id=None)
            setattr(row, field, value)
            session.add(row)
            with pytest.raises(FactAnchorError):
                session.commit()
            session.rollback()

    def test_lectura_normal_tras_persistir(self, session):
        self._row(session)
        from sqlalchemy import select

        loaded = session.execute(select(FactAnchor)).scalar_one()
        assert loaded.value_text == "$54.20"
        assert loaded.item == "Item 1.01"

    def test_rehacer_la_verificacion_tras_mutar_no_abre_puerta(self, session):
        # El bypass del auditor r4: mutar y "re-sellar" la fila no vale -
        # la revalidacion va contra el body retenido, no contra un checksum.
        row = FactAnchor.from_spec(_build(), body=BODY, tenant_id=None)
        row.value_text = "$99.99"
        session.add(row)
        with pytest.raises(FactAnchorError):
            session.commit()
        session.rollback()

    def test_from_spec_persiste_los_campos_del_builder(self, session):
        row = self._row(session)
        assert row.id is not None
        assert row.value_text == "$54.20"
        assert row.item == "Item 1.01"
        assert row.body_sha256 == sha256_text(BODY)

    def test_update_de_una_fila_esta_bloqueado(self, session):
        row = self._row(session)
        row.value_text = "$99.99"
        with pytest.raises(FactAnchorError):
            session.commit()

    def test_delete_de_una_fila_esta_bloqueado(self, session):
        row = self._row(session)
        session.delete(row)
        with pytest.raises(FactAnchorError):
            session.commit()
