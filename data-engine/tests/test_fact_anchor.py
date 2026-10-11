"""Tests adversariales del anclaje de datos a la frase exacta del filing.

Regla de la casa: un dato sin ancla verificable no se publica; lo inferido se
etiqueta INFERIDO; la ausencia nunca se representa como 0 ni como cadena vacia.
"""

import pytest

from app.models.entities import FactAnchor
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


def _build(**over):
    args = dict(
        body=BODY,
        accession="0001193125-26-004321",
        filename="d123456d8k.htm",
        field="offer_price",
        value_text="$54.20",
        label="OFICIAL",
        quote="will receive $54.20 in cash for each share of Beta common stock.",
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

    def test_inferido_es_etiqueta_valida(self):
        assert _build(label="INFERIDO").label == "INFERIDO"

    def test_valor_vacio_es_error_la_ausencia_nunca_es_cadena_vacia(self):
        with pytest.raises(FactAnchorError, match="valor"):
            _build(value_text="   ")

    def test_campo_vacio_es_error(self):
        with pytest.raises(FactAnchorError):
            _build(field=" ")

    def test_cita_que_no_esta_en_el_documento_no_ancla(self):
        with pytest.raises(FactAnchorError):
            _build(quote="will receive $99.99 in cash")


class TestVerifyAnchor:
    def test_ancla_valida_verifica(self):
        assert verify_anchor(BODY, _build()) is True

    def test_documento_distinto_no_verifica_por_sha(self):
        anchor = _build()
        assert verify_anchor(BODY + " ", anchor) is False

    def test_offset_manipulado_no_verifica(self):
        anchor = _build()
        moved = FactAnchorSpec(
            **{**anchor.__dict__, "quote_offset": anchor.quote_offset - 1}
        )
        assert verify_anchor(BODY, moved) is False

    def test_cita_manipulada_no_verifica(self):
        anchor = _build()
        tampered = FactAnchorSpec(**{**anchor.__dict__, "quote": anchor.quote.replace("54.20", "54.21")})
        assert verify_anchor(BODY, tampered) is False


class TestFactAnchorModel:
    def test_unicidad_incluye_tenant_como_el_resto_de_tablas(self):
        constraints = [
            c for c in FactAnchor.__table__.constraints if c.__class__.__name__ == "UniqueConstraint"
        ]
        assert any(
            [col.name for col in c.columns]
            == ["tenant_id", "accession_number", "filename", "field", "quote_offset"]
            for c in constraints
        )

    def test_tenant_id_indexado(self):
        assert FactAnchor.__table__.c.tenant_id.index is True
