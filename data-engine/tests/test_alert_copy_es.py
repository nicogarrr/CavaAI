"""Copys visibles de alertas y claims en español con cifras formateadas.

Bug reportado con capturas de la app: textos en inglés ("RKLB revenue is
200966000000.000000 for FY2025."), la misma afirmación repetida en el cuerpo
de la alerta y cifras crudas de la columna Numeric(24, 6). Estos tests fijan
el contrato: todo texto persistido para el usuario nace en es-ES y con la
cifra compacta de la casa (M / mil M).
"""

from decimal import Decimal
from types import SimpleNamespace

from app.services.number_format import format_compact_es, format_number_es
from app.services.thesis_service import _metric_claim_statement


class TestFormatNumberEs:
    def test_grouping_and_decimal_comma(self):
        assert format_number_es(1234.5) == "1.234,5"

    def test_trailing_fraction_zeros_drop(self):
        assert format_number_es(Decimal("24.00")) == "24"

    def test_none_and_garbage_are_honest(self):
        assert format_number_es(None) is None
        assert format_number_es("not-a-number") is None


class TestFormatCompactEs:
    def test_thousands_of_millions(self):
        assert format_compact_es(Decimal("200966000000.000000")) == "200,97 mil M"

    def test_millions(self):
        assert format_compact_es(24_000_000) == "24 M"

    def test_small_values_stay_plain(self):
        assert format_compact_es(Decimal("0.25")) == "0,25"

    def test_negative_scales(self):
        assert format_compact_es(-1_500_000_000) == "-1,5 mil M"

    def test_non_numeric_is_none(self):
        assert format_compact_es(None) is None


class TestMetricClaimStatement:
    def test_spanish_with_compact_value_and_currency(self):
        fact = SimpleNamespace(
            value=Decimal("200966000000.000000"), unit="USD", period="FY2025"
        )
        statement = _metric_claim_statement("RKLB", "revenue", fact)
        assert statement == "RKLB: ingresos de 200,97 mil M USD (FY2025)."

    def test_metric_label_fallback_quotes_raw_key(self):
        # Clave desconocida: se muestra como dato crudo entre comillas, no
        # "humanizada" a una frase en inglés dentro del texto en español.
        fact = SimpleNamespace(value=Decimal("12.5"), unit="x", period="Q2 2026")
        statement = _metric_claim_statement("META", "gross_margin", fact)
        assert statement == 'META: dato "gross_margin" de 12,5 (Q2 2026).'

    def test_all_snapshot_metrics_have_spanish_labels(self):
        # El conjunto de métricas del snapshot es cerrado y la tabla lo cubre:
        # ninguna clave real puede caer en el fallback.
        from app.services.thesis_service import _METRIC_LABELS_ES
        from app.valuation.financial_snapshot import DURATION_METRICS, INSTANT_METRICS

        for metric in (*DURATION_METRICS, *INSTANT_METRICS):
            assert metric in _METRIC_LABELS_ES, f"{metric} sin etiqueta es-ES"

    def test_new_metric_labels_render_spanish(self):
        fact = SimpleNamespace(value=Decimal("12300000000"), unit="USD", period="FY2025")
        assert _metric_claim_statement("META", "operating_cash_flow", fact) == (
            "META: flujo de caja operativo de 12,3 mil M USD (FY2025)."
        )
        assert _metric_claim_statement("META", "total_debt", fact) == (
            "META: deuda total de 12,3 mil M USD (FY2025)."
        )

    def test_no_raw_decimal_places_or_english(self):
        fact = SimpleNamespace(
            value=Decimal("200966000000.000000"), unit="USD", period="FY2025"
        )
        statement = _metric_claim_statement("RKLB", "revenue", fact)
        assert "200966000000" not in statement
        assert " is " not in statement and " for " not in statement
