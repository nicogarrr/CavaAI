"""C4: contrato puerta por puerta de los gates de ingesta, y el guardian de red.

Tres de las diez puertas se pueden silenciar omitiendo su clave, y eso es
justo lo que no debe pasar: `no_lookahead` sin `expected.as_of` no tiene contra
que comparar, `official_only_if_index_verified` sin `expected.index` deja
cualquier hecho declararse OFICIAL, y `absent_fields_reported_as_null` sin
`expected.absent_metrics` no tiene fabricacion que detectar. Cada puerta se
prueba aqui con su caso minimo (que tiene que fallar) y con su caso bueno.

El guardian de red se prueba contra si mismo: si el harness no bloqueara
`socket.connect`, uno de estos tests lo notaria.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from evals.ingest import harness
from evals.ingest.ingest_gates import (
    GATES,
    MIN_CASES,
    MIN_DEGRADATION_CASES,
    MIN_FAMILY_CASES,
    MIN_NEGATIVE_CONTROLS,
    MIN_SEC_CASES,
    NON_SKIPPABLE_GATES,
    applies_to,
    gate_absent_fields_reported_as_null,
    gate_duplicates_collapsed,
    gate_extracted_values_match_fixture,
    gate_fixture_schema_valid,
    gate_negative_controls_present,
    gate_no_lookahead,
    gate_official_only_if_index_verified,
    gate_period_attribution_correct,
    gate_source_types_declared,
    gate_units_consistent,
)

SEC_FACTS = [
    {
        "metric": "revenue",
        "period": "2025-12-31:FY",
        "value": 5_000_000_000.0,
        "unit": "USD",
        "fiscal_year": 2025,
        "fiscal_quarter": "FY",
        "source_type": "SEC",
        "is_reported": True,
    }
]


def _case(observed=None, expected=None, **extra):
    return {
        "id": "contract-001",
        "family": "sec",
        "scenario": "sec_companyfacts",
        "expected": expected or {},
        "observed": observed if observed is not None else {"facts": list(SEC_FACTS)},
        **extra,
    }


def _full_expected(**overrides):
    base = {
        "as_of": "2026-10-01",
        "tolerance": {"relative": "0", "absolute": "0.000001"},
        "facts": [
            {
                "metric": "revenue",
                "period": "2025-12-31:FY",
                "value": 5_000_000_000,
                "unit": "USD",
                "fiscal_year": 2025,
                "fiscal_quarter": "FY",
            }
        ],
        "absent_metrics": ["gross_profit"],
        "index": {"verified": [], "official": [], "unverified": []},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Las tres puertas no omitibles fallan cuando falta su clave
# --------------------------------------------------------------------------


def test_no_lookahead_fails_without_as_of():
    expected = _full_expected()
    expected.pop("as_of")
    result = gate_no_lookahead(_case(expected=expected))
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]
    assert "as_of" in result["details"][0]


def test_no_lookahead_fails_with_a_nonsense_as_of():
    result = gate_no_lookahead(_case(expected=_full_expected(as_of="ayer")))
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]


def test_no_lookahead_catches_a_future_fact():
    observed = {"facts": [
        *SEC_FACTS,
        {
            "metric": "revenue",
            "period": "2999-12-31:FY",
            "value": 42_000_000_000.0,
            "unit": "USD",
            "fiscal_year": 2999,
            "fiscal_quarter": "FY",
            "source_type": "SEC",
            "is_reported": True,
        },
    ]}
    result = gate_no_lookahead(_case(observed=observed, expected=_full_expected()))
    assert result["passed"] is False
    assert "look-ahead" in result["details"][0]


def test_no_lookahead_catches_a_forbidden_value_inside_a_real_period():
    expected = _full_expected(forbidden_values=[999_000_000_000])
    observed = {"facts": [{**SEC_FACTS[0], "value": 999_000_000_000.0}]}
    result = gate_no_lookahead(_case(observed=observed, expected=expected))
    assert result["passed"] is False
    assert "look-ahead" in result["details"][0]


def test_official_only_if_index_verified_fails_without_the_index_block():
    expected = _full_expected()
    expected.pop("index")
    result = gate_official_only_if_index_verified(_case(expected=expected))
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]
    assert "index" in result["details"][0]


def test_official_only_if_index_verified_fails_on_an_incomplete_index_block():
    result = gate_official_only_if_index_verified(
        _case(expected=_full_expected(index={"official": ["0000000001-25-000001"]}))
    )
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]


def test_absent_fields_fails_without_absent_metrics():
    expected = _full_expected()
    expected["absent_metrics"] = None
    result = gate_absent_fields_reported_as_null(_case(expected=expected))
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]


def test_absent_fields_catches_a_fabricated_metric():
    observed = {"facts": [
        *SEC_FACTS,
        {
            "metric": "gross_profit",
            "period": "2025-12-31:FY",
            "value": 2_000_000_000.0,
            "unit": "USD",
            "fiscal_year": 2025,
            "fiscal_quarter": "FY",
            "source_type": "SEC",
            "is_reported": True,
        },
    ]}
    result = gate_absent_fields_reported_as_null(_case(observed=observed,
                                                      expected=_full_expected()))
    assert result["passed"] is False
    assert "gross_profit" in result["details"][0]


# --------------------------------------------------------------------------
# official_only_if_index_verified: la regla de oro
# --------------------------------------------------------------------------


def _index_case(verified, official, unverified, provenance, index_verification):
    return _case(
        observed={
            "facts": list(SEC_FACTS),
            "provenance": provenance,
            "index_verification": index_verification,
        },
        expected=_full_expected(
            index={"verified": verified, "official": official, "unverified": unverified}
        ),
    )


def test_official_is_allowed_when_the_index_verified_the_filing():
    accession = "0001193125-26-000001"
    result = gate_official_only_if_index_verified(_index_case(
        [accession], [accession], [],
        {"revenue@2025-12-31:FY": {"origin": "OFICIAL", "accession": accession}},
        {accession: {"verified": True, "status": "ingested"}},
    ))
    assert result["passed"] is True, result["details"]


def test_official_is_refused_when_the_index_rejected_the_filing():
    accession = "0001193125-26-000001"
    result = gate_official_only_if_index_verified(_index_case(
        [accession], [accession], [],
        {"revenue@2025-12-31:FY": {"origin": "OFICIAL", "accession": accession}},
        {accession: {"verified": False, "status": "rejected", "reason": "sha256 distinto"}},
    ))
    assert result["passed"] is False
    assert "sha256 distinto" in result["details"][0]


def test_official_is_refused_without_a_verification_record():
    accession = "0001193125-26-000001"
    result = gate_official_only_if_index_verified(_index_case(
        [accession], [accession], [],
        {"revenue@2025-12-31:FY": {"origin": "OFICIAL", "accession": accession}},
        {},
    ))
    assert result["passed"] is False
    assert "nunca se evaluo" in result["details"][0]


def test_unindexed_filing_can_never_come_out_official():
    accession = "0001193125-26-000009"
    result = gate_official_only_if_index_verified(_index_case(
        [], [], [accession],
        {"revenue@2025-12-31:FY": {"origin": "OFICIAL", "accession": accession}},
        {accession: {"verified": False, "status": "rejected", "reason": "sin indice"}},
    ))
    assert result["passed"] is False
    assert "sin verificar" in " ".join(result["details"])


def test_recall_of_index_verification_is_enforced():
    """Un accession verificado que no llega a ningun hecho es un recall de cero."""
    accession = "0001193125-26-000001"
    result = gate_official_only_if_index_verified(_index_case(
        [accession], [accession], [],
        {},
        {accession: {"verified": True, "status": "ingested"}},
    ))
    assert result["passed"] is False
    assert "recall" in result["details"][0]


def test_a_declared_official_fact_without_declared_accession_is_refused():
    result = gate_official_only_if_index_verified(_index_case(
        [], [], [],
        {"revenue@2025-12-31:FY": {"origin": "OFICIAL", "accession": None}},
        {},
    ))
    assert result["passed"] is False
    assert "sin accession declarado" in " ".join(result["details"])


# --------------------------------------------------------------------------
# Las otras siete puertas muerden
# --------------------------------------------------------------------------


def test_values_gate_fails_on_a_wrong_number():
    result = gate_extracted_values_match_fixture(
        _case(expected=_full_expected(facts=[{
            "metric": "revenue", "period": "2025-12-31:FY", "value": 4_000_000_000,
            "unit": "USD", "fiscal_year": 2025, "fiscal_quarter": "FY"}]))
    )
    assert result["passed"] is False
    assert "no es el valor declarado" in result["details"][1]


def test_values_gate_fails_when_a_period_holds_two_different_numbers():
    observed = {"facts": [SEC_FACTS[0], {**SEC_FACTS[0], "value": 999_000_000_000.0}]}
    result = gate_extracted_values_match_fixture(_case(observed=observed,
                                                       expected=_full_expected()))
    assert result["passed"] is False
    assert "cifra ambigua" in " ".join(result["details"])


def test_values_gate_respects_the_declared_tolerance():
    observed = {"facts": [{**SEC_FACTS[0], "value": 5_000_000_000.004}]}
    tight = _full_expected()
    loose = _full_expected(tolerance={"relative": "0", "absolute": "0.01"})
    assert not gate_extracted_values_match_fixture(_case(observed=observed, expected=tight))[
        "passed"
    ]
    assert gate_extracted_values_match_fixture(_case(observed=observed, expected=loose))["passed"]


def test_values_gate_fails_on_a_second_row_of_another_emitter():
    observed = {"facts": [SEC_FACTS[0], {**SEC_FACTS[0], "value": 999_000_000_000.0}]}
    result = gate_extracted_values_match_fixture(_case(observed=observed,
                                                       expected=_full_expected()))
    assert result["passed"] is False


def test_values_gate_fails_when_the_case_declares_nothing_at_all():
    expected = _full_expected()
    expected["facts"] = []
    expected.pop("extracts_nothing", None)
    result = gate_extracted_values_match_fixture(_case(expected=expected))
    assert result["passed"] is False
    assert "el gate no puede omitirse" in result["details"][0]


def test_period_gate_catches_a_fiscal_year_slip():
    result = gate_period_attribution_correct(_case(expected=_full_expected(facts=[{
        "metric": "revenue", "period": "2025-12-31:FY", "value": 5_000_000_000,
        "unit": "USD", "fiscal_year": 2024, "fiscal_quarter": "FY"}])))
    assert result["passed"] is False
    assert "fy=2025" in result["details"][1]


def test_period_gate_catches_a_fact_that_never_landed_on_its_period():
    result = gate_period_attribution_correct(_case(expected=_full_expected(facts=[{
        "metric": "revenue", "period": "2025-09-30:Q3", "value": 1_200_000_000,
        "unit": "USD", "fiscal_year": None, "fiscal_quarter": "Q3"}])))
    assert result["passed"] is False
    assert "no se atribuyo" in " ".join(result["details"])


def test_period_gate_catches_an_extra_quarter_the_fixture_never_declared():
    observed = {"facts": [
        SEC_FACTS[0],
        {**SEC_FACTS[0], "period": "2025-03-31:Q1", "fiscal_year": None,
         "fiscal_quarter": "Q1", "value": 1_000_000_000.0},
    ]}
    result = gate_period_attribution_correct(
        _case(observed=observed, expected=_full_expected(periods={"revenue": ["2025-12-31:FY"]}))
    )
    assert result["passed"] is False
    assert "periodos" in result["details"][-1]


def test_period_gate_checks_the_normalised_statements():
    expected = _full_expected(statements=[{
        "statement_type": "income", "period": "2025-12-31:FY",
        "fiscal_year": 2025, "fiscal_quarter": "FY"}])
    result = gate_period_attribution_correct(_case(
        observed={"facts": list(SEC_FACTS), "statements": [
            {"statement_type": "income", "period": "2025-12-31:FY",
             "fiscal_year": 2024, "fiscal_quarter": "FY"}]},
        expected=expected,
    ))
    assert result["passed"] is False
    assert "declaracion income" in " ".join(result["details"])


def test_units_gate_catches_a_mixed_unit_in_one_metric():
    observed = {"facts": [SEC_FACTS[0], {**SEC_FACTS[0], "period": "2024-12-31:FY",
                                         "unit": "EUR"}]}
    result = gate_units_consistent(_case(observed=observed, expected=_full_expected()))
    assert result["passed"] is False
    assert "unidades mezcladas" in result["details"][0]


def test_units_gate_catches_a_unit_the_case_does_not_declare():
    result = gate_units_consistent(_case(expected=_full_expected(units={"revenue": "EUR"})))
    assert result["passed"] is False
    assert "unidades" in result["details"][0]


def test_source_types_gate_catches_a_source_the_family_does_not_allow():
    observed = {"facts": [{**SEC_FACTS[0], "source_type": "TIKTOK"}]}
    result = gate_source_types_declared(_case(observed=observed, expected=_full_expected()))
    assert result["passed"] is False
    assert "TIKTOK" in result["details"][0]


def test_source_types_gate_catches_a_declared_source_that_does_not_match():
    result = gate_source_types_declared(
        _case(expected=_full_expected(source_types={"revenue": "ESEF"}))
    )
    assert result["passed"] is False
    assert "ESEF" in result["details"][0]


def test_duplicates_gate_catches_two_rows_for_one_period():
    observed = {"facts": [SEC_FACTS[0], {**SEC_FACTS[0], "value": 4_000_000_000.0}]}
    result = gate_duplicates_collapsed(_case(observed=observed))
    assert result["passed"] is False
    assert "duplicado" in result["details"][0]


def test_fixture_schema_gate_catches_a_case_with_no_tolerance():
    expected = _full_expected()
    expected.pop("tolerance")
    result = gate_fixture_schema_valid(_case(expected=expected))
    assert result["passed"] is False
    assert "tolerancia" in result["details"][0]


def test_fixture_schema_gate_catches_a_missing_fixture_file():
    result = gate_fixture_schema_valid(_case(
        scenario_args={"companyfacts": "sec/no-existe.json"}, expected=_full_expected()
    ))
    assert result["passed"] is False
    assert "inexistente" in result["details"][0]


def test_fixture_schema_gate_catches_a_fixture_without_the_synthetic_declaration():
    tmp = Path(harness.FIXTURES) / "sec" / "_contract_sin_origen.json"
    tmp.write_text('{"facts": {}}', encoding="utf-8")
    try:
        result = gate_fixture_schema_valid(_case(
            scenario_args={"companyfacts": "sec/_contract_sin_origen.json"},
            expected=_full_expected(),
        ))
        assert result["passed"] is False
        assert "synthetic_fixture" in result["details"][0]
    finally:
        tmp.unlink(missing_ok=True)


def test_negative_controls_gate_fails_on_a_thin_dataset():
    result = gate_negative_controls_present({
        "dataset_summary": {
            "cases": 10, "negative_controls": 1, "degradation_cases": 0,
            "families": {"sec": 10, "fmp": 0, "esef": 0},
            "negative_controls_not_declared": ["no_lookahead"],
        }
    })
    assert result["passed"] is False
    joined = " ".join(result["details"])
    assert "cases=10" in joined
    assert "sin expect_gate_failure" in joined


def test_negative_controls_gate_thresholds_are_the_documented_ones():
    assert (MIN_CASES, MIN_NEGATIVE_CONTROLS, MIN_DEGRADATION_CASES) == (60, 8, 5)
    assert MIN_FAMILY_CASES == 12
    assert MIN_SEC_CASES == 25


def test_every_gate_has_the_three_field_contract():
    for name, gate in GATES.items():
        result = gate({})
        assert set(result) == {"gate", "passed", "details"}, name
        assert result["gate"] == name, name
        assert isinstance(result["passed"], bool), name
        assert isinstance(result["details"], list) and result["details"], name


def test_non_skippable_gates_run_even_when_the_case_opts_out():
    for name in NON_SKIPPABLE_GATES:
        assert applies_to({"applies_to": []}, name) is True, name
    assert applies_to({"applies_to": ["no_lookahead"]}, "units_consistent") is False
    assert applies_to({}, "units_consistent") is True


# --------------------------------------------------------------------------
# Guardian de red
# --------------------------------------------------------------------------


def test_no_network_blocks_outbound_connections():
    with harness.no_network():
        with pytest.raises(harness.NetworkBlocked):
            socket.create_connection(("example.com", 443), timeout=1)
        with pytest.raises(harness.NetworkBlocked):
            socket.getaddrinfo("data.sec.gov", 443)
        with pytest.raises(harness.NetworkBlocked):
            socket.socket().connect(("financialmodelingprep.com", 443))


def test_no_network_allows_loopback():
    with harness.no_network():
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        try:
            client = socket.socket()
            client.connect(listener.getsockname())
            client.close()
        finally:
            listener.close()


def test_no_network_restores_the_socket_module():
    real_connect = socket.socket.connect
    real_getaddrinfo = socket.getaddrinfo
    with harness.no_network():
        assert socket.socket.connect is not real_connect
    assert socket.socket.connect is real_connect
    assert socket.getaddrinfo is real_getaddrinfo


def test_harness_runs_a_case_without_touching_the_network():
    case = {
        "id": "contract-offline",
        "family": "sec",
        "scenario": "sec_companyfacts",
        "scenario_args": {
            "companyfacts": "sec/companyfacts_calendar_fy.json",
            "submissions": "sec/submissions_calendar_fy.json",
        },
    }
    observation = harness.run_case(case)
    assert observation["status"] == "ok"
    assert observation["errors"] == []
    assert any(fact["metric"] == "revenue" for fact in observation["facts"])
    assert all(
        request.startswith("https://") for request in observation["requests"]
    )


def test_harness_rejects_an_unknown_scenario():
    with pytest.raises(KeyError):
        harness.run_case({"id": "x", "scenario": "no-existe"})


def test_llm_classifier_is_disabled_inside_the_harness():
    """El clasificador de anomalias es un LLM; un eval determinista no lo llama."""
    from app.services import jev_gates

    real = jev_gates.mark_only
    with harness._llm_disabled():
        assert jev_gates.mark_only is not real
        assert jev_gates.mark_only("data_anomaly", "texto", "instrucciones", {}) is None
    assert jev_gates.mark_only is real


def test_dataset_declares_every_measured_gap():
    """Los controles negativos que fotografian un defecto real estan declarados.

    Un `expect_gate_failure` que nadie ha ledo es un test que nadie va a quitar
    cuando el defecto se arregle. Cada uno va acompanado del caso y del defecto
    en `known_gaps`, y este test exige que ambos coincidan.
    """
    from evals.ingest.ingest_gates import GATES

    dataset = json.loads(
        (harness.ROOT / "evals" / "ingest" / "ingest_v1.json").read_text(encoding="utf-8")
    )
    negatives = {c["id"]: c for c in dataset["cases"] if c.get("expect_gate_failure")}
    gaps = dataset.get("known_gaps") or []
    assert gaps, "el dataset no declara sus huecos medidos"
    for gap in gaps:
        case = negatives.get(gap["case"])
        assert case is not None, f"{gap['case']} no es un control negativo"
        assert case["expect_gate_failure"] == gap["gate"], gap["case"]
        assert gap["gate"] in GATES, gap["gate"]
        assert len(gap["defect"]) > 60, f"{gap['case']} sin explicar el defecto"
    measured = {
        "neg-001-lookahead-anclado-filtrado",
        "neg-002-epoch-en-la-etiqueta-de-periodo",
        "neg-003-fila-de-otro-emisor",
        "neg-013-filas-duplicadas-del-proveedor",
        "neg-015-ixbrl-con-scale-y-sign",
    }
    assert measured <= {gap["case"] for gap in gaps}
