"""Hard gates for point-in-time thesis backtests.

Same contract as :mod:`evals.gates`: a pure function ``f(case) -> {"gate",
"passed", "details"}`` over a frozen cell artifact. No database, no network, no
LLM. A dataset declares which gates a case exercises (``applies_to``, opt-out)
and which single gate a case is *supposed* to fail (``expect_gate_failure``), and
``scripts/run_backtest_evals.py`` fails the build if a gate never ran.

The gates exist because the failure mode of a backtest is not a crash, it is a
green result. Every gate here closes a specific way to get a green result that
does not mean anything:

- ``no_lookahead`` — the replay saw a period that ends after its own cutoff.
- ``evidence_cutoff_respected`` — a fact or claim used evidence filed later.
- ``insufficient_data_not_filled_with_price`` — an abstention was quietly
  completed with the current price, which is the single easiest way to turn
  "we knew nothing" into a 0% return and call it a thesis failure.
- ``probabilities_sum_to_one`` / ``bear_le_base_le_bull`` — scenario weights
  that do not add up, or a bear case above its own base case.
- ``degraded_reason_present_when_degraded`` — a cell quietly downgraded.
- ``source_coverage_score_present`` / ``claims_have_evidence_ratio_recorded`` —
  coverage asserted instead of measured.
- ``no_invented_numbers`` — a claim quoting a number no frozen fact supports.
- ``idempotent_replay`` — a replay that does not reproduce itself, which makes
  every other number in the run unverifiable.
- ``net_neutral_honest`` — the classic tell of a backtest with no real
  information: every date produces the same fair value.

A gate listed in :data:`NON_SKIPPABLE_GATES` fails when the key it needs is
absent, rather than reporting "no aplica". Silently not applicable is
indistinguishable from silently broken.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The repo root, so `evals.gates` resolves when the runner is executed as a
# script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Reused on purpose: the Spanish decimal comma ("1,2" is one point two) is the
# difference between catching an invented magnitude and normalising it into a
# plausible-looking pass.
from evals.gates import _norm_number  # noqa: E402

_NUMBER_RE = re.compile(r"-?\d[\d.,]*")

VALID_STATUSES = {
    "ok",
    "insufficient_data",
    "not_yet_published",
    "rejected_lookahead",
    "error",
}
ABSTENTION_STATUSES = VALID_STATUSES - {"ok"}
VALID_VERDICTS = {"bullish", "bearish", "neutral"}


def _result(gate: str, passed: bool, details: list[str]) -> dict:
    return {"gate": gate, "passed": passed, "details": details}


def _artifact(case: dict) -> dict:
    return case.get("artifact") or {}


def _frozen_by_metric(case: dict) -> dict[str, set[float]]:
    """Every frozen value per metric.

    A metric can be frozen at several dates (FY2022 revenue 820, FY2023 900,
    FY2024 1000...), so a value may be a scalar or a list. Collapsing them into
    a per-metric set is what lets a claim quote any year's figure without the
    gate having to know the vintage.
    """
    out: dict[str, set[float]] = {}
    for metric, value in (case.get("frozen_facts") or {}).items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            number = _norm_number(str(item))
            if number is not None:
                out.setdefault(metric, set()).add(number)
    return out


def _tolerance_value(number: float) -> bool:
    return number in {0, 1, 2, 3}


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------- non-skippable


def gate_no_lookahead(case: dict) -> dict:
    """No period after the cutoff, and every violation honestly labelled.

    Non-skippable. Without ``expected.as_of`` there is no cutoff to check
    against, and a look-ahead audit that cannot name its own date is not an
    audit.
    """
    expected = case.get("expected") or {}
    artifact = _artifact(case)
    gate = "no_lookahead"
    expected_as_of = expected.get("as_of")
    if expected_as_of is None:
        return _result(
            gate,
            False,
            ["falta expected.as_of: el gate no puede omitirse"],
        )
    if artifact.get("as_of") != expected_as_of:
        return _result(
            gate,
            False,
            [f"artifact.as_of {artifact.get('as_of')} != expected.as_of {expected_as_of}"],
        )

    problems: list[str] = []
    # Two independent lists, because not every engine routes through the
    # point-in-time snapshot: four of the eight valuation engines query
    # ``FinancialFact`` directly, so their periods only ever appear in the
    # engine's own trace. Auditing ``used_periods`` alone would let every
    # sector-engine cell pass this gate vacuously.
    audited = 0
    for key in ("used_periods", "engine_trace_periods"):
        for entry in artifact.get(key) or []:
            audited += 1
            end_date = entry.get("end_date")
            if end_date is None:
                problems.append(
                    f"{key}/{entry.get('metric')}: periodo sin fecha de fin "
                    f"({entry.get('raw')!r}); no se puede probar que fuera anterior al corte"
                )
            elif str(end_date) > str(expected_as_of):
                problems.append(
                    f"{key}/{entry.get('metric')}: periodo hasta {end_date} "
                    f"posterior al corte {expected_as_of}"
                )
            published = entry.get("source_published_on")
            if published is not None and str(published) > str(expected_as_of):
                problems.append(
                    f"{key}/{entry.get('metric')}: fuente publicada el {published}, "
                    "despues del corte"
                )
    if audited == 0 and artifact.get("status") == "ok":
        problems.append(
            "la celda no declara ningun periodo auditado (used_periods ni "
            "engine_trace_periods): el gate pasaria sin comprobar nada"
        )

    for entry in artifact.get("lookahead_violations_detail") or []:
        end_date = entry.get("end_date")
        if end_date is None or str(end_date) <= str(expected_as_of):
            problems.append(
                f"violacion declarada para {entry.get('metric')} con end_date {end_date}: "
                f"no es posterior al corte {expected_as_of}, asi que la lista infla el recuento"
            )

    declared = artifact.get("lookahead_violations")
    if declared and artifact.get("status") == "ok":
        problems.append(
            f"la celda declara {len(declared)} violacion(es) de look-ahead y aun asi "
            "publica fair_value con status=ok"
        )
    return _result(gate, not problems, problems[:10])


def gate_evidence_cutoff_respected(case: dict) -> dict:
    """The cutoff that produced the number is stated, dated and not in the future.

    Non-skippable. A fair value without the date its evidence was cut at is a
    number with no provenance, and a cutoff later than the cell's own ``as_of``
    means the replay reached forward.
    """
    expected = case.get("expected") or {}
    artifact = _artifact(case)
    gate = "evidence_cutoff_respected"
    expected_cutoff = expected.get("evidence_cutoff")
    if expected_cutoff is None:
        return _result(
            gate,
            False,
            ["falta expected.evidence_cutoff: el gate no puede omitirse"],
        )
    cutoff = artifact.get("evidence_cutoff")
    if cutoff is None:
        return _result(gate, False, ["la celda no declara evidence_cutoff"])
    if str(cutoff) != str(expected_cutoff):
        return _result(
            gate,
            False,
            [f"evidence_cutoff {cutoff} != esperado {expected_cutoff}"],
        )
    problems: list[str] = []
    if artifact.get("as_of") and str(cutoff) > str(artifact["as_of"]):
        problems.append(
            f"evidence_cutoff {cutoff} es posterior al as_o de la celda {artifact['as_of']}"
        )
    for claim in artifact.get("claims") or []:
        cited = claim.get("evidence_published_on")
        if cited is not None and str(cited) > str(cutoff):
            problems.append(
                f"claim {str(claim.get('text'))[:50]!r} cita evidencia del {cited}, "
                f"posterior al corte {cutoff}"
            )
    return _result(gate, not problems, problems[:10])


def gate_no_invented_numbers(case: dict) -> dict:
    """Every number in a claim comes from a frozen fact of the same metric.

    Non-skippable: with no ``frozen_facts`` there is nothing to check against,
    and reusing :func:`evals.gates._norm_number` keeps the Spanish decimal
    comma (``1,2`` is one point two, not twelve) from being normalised into a
    plausible-looking pass.
    """
    artifact = _artifact(case)
    gate = "no_invented_numbers"
    frozen = case.get("frozen_facts")
    if frozen is None:
        return _result(
            gate,
            False,
            ["el caso no declara frozen_facts: el gate no puede omitirse"],
        )
    by_metric = _frozen_by_metric(case)
    known = set().union(*by_metric.values()) if by_metric else set()
    problems: list[str] = []
    for claim in artifact.get("claims") or []:
        text = str(claim.get("text") or "")
        if not text:
            continue
        metric = claim.get("metric")
        pool = by_metric.get(metric, set()) if metric else known
        for match in _NUMBER_RE.findall(text):
            number = _norm_number(match)
            if number is None or _tolerance_value(number):
                continue
            if number not in pool:
                label = f" para {metric!r}" if metric else ""
                problems.append(f"numero sin frozen fact{label} en claim: {match}")
    return _result(gate, not problems, problems[:10])


def gate_idempotent_replay(case: dict) -> dict:
    """Re-running the same cell produces the same hash.

    Non-skippable. A backtest whose replay is not reproducible cannot be
    audited, and the tell is invisible in the output numbers: everything looks
    plausible and none of it can be checked.
    """
    artifact = _artifact(case)
    gate = "idempotent_replay"
    first = artifact.get("replay_hash")
    again = artifact.get("replay_hash_again")
    if not first or not again:
        return _result(
            gate,
            False,
            ["faltan replay_hash / replay_hash_again: el gate no puede omitirse"],
        )
    if first != again:
        return _result(gate, False, [f"hash de replay inestable: {first} != {again}"])
    return _result(gate, True, [f"hash estable {first[:12]}"])


def gate_source_coverage_score_present(case: dict) -> dict:
    """Coverage is a measured integer in [0, 100], not a null that reads as fine.

    Non-skippable: ``None`` is the value a cell gets when nobody computed it,
    and averaging it away hides exactly the cells that have no evidence.
    """
    artifact = _artifact(case)
    gate = "source_coverage_score_present"
    score = artifact.get("source_coverage_score")
    if score is None:
        # Null is an honest value for a cell with no claims at all: there is
        # nothing to cover, so coverage is undefined rather than zero. It is NOT
        # acceptable on a cell that does have claims — that is the audit simply
        # never having run, and averaging those away hides the worst cells.
        if artifact.get("n_claims") == 0:
            return _result(gate, True, ["celda sin claims: cobertura no definida"])
        return _result(
            gate,
            False,
            [
                f"source_coverage_score null con {artifact.get('n_claims')} claim(s): "
                "el gate no puede omitirse"
            ],
        )
    if not isinstance(score, int) or isinstance(score, bool):
        return _result(gate, False, [f"source_coverage_score no es un entero: {score!r}"])
    if not 0 <= score <= 100:
        return _result(gate, False, [f"source_coverage_score fuera de rango: {score}"])
    return _result(gate, True, [f"source_coverage_score={score}"])


# ------------------------------------------------------------------- abstention


def gate_insufficient_data_not_filled_with_price(case: dict) -> dict:
    """An abstention carries no number. Ever.

    This is the gate that matters most for the product question. Filling an
    ``insufficient_data`` cell with the current price is not a rounding
    convenience: it converts "we had no view" into "the view was worth zero",
    which drags the hit rate down and makes an honest abstention look like a
    failed thesis.
    """
    artifact = _artifact(case)
    gate = "insufficient_data_not_filled_with_price"
    status = artifact.get("status")
    problems: list[str] = []
    if status not in VALID_STATUSES:
        problems.append(f"status desconocido: {status!r}")
    if status in ABSTENTION_STATUSES:
        if artifact.get("fair_value") is not None:
            problems.append(
                f"status={status} pero fair_value={artifact.get('fair_value')}: "
                "una abstención no lleva valor"
            )
        if artifact.get("bear_value") is not None or artifact.get("bull_value") is not None:
            problems.append(f"status={status} pero trae escenarios valorados")
        if not (artifact.get("degraded_reason") or "").strip():
            problems.append(f"status={status} sin motivo declarado")
    if status == "ok" and artifact.get("fair_value") is None:
        problems.append("status=ok sin fair_value")
    if status == "ok" and artifact.get("current_price") is None:
        problems.append("status=ok sin precio de referencia: el upside no es calculable")
    return _result(gate, not problems, problems)


# ------------------------------------------------------------------- coherence


def gate_probabilities_sum_to_one(case: dict) -> dict:
    """Scenario probabilities, when declared, add up to one.

    A cell that declares no scenarios is reported as such rather than failed:
    not every thesis has one, and the dataset coverage check is what stops this
    gate from quietly dying.
    """
    artifact = _artifact(case)
    gate = "probabilities_sum_to_one"
    scenarios = artifact.get("scenario_probabilities")
    if not scenarios:
        return _result(gate, True, ["la celda no declara escenario: no aplica"])
    try:
        total = sum(float(value) for value in scenarios.values() if value is not None)
    except (TypeError, ValueError):
        return _result(gate, False, [f"probabilidades no numericas: {scenarios}"])
    passed = abs(total - 1.0) <= 0.01
    return _result(
        gate,
        passed,
        [f"suma={total:.4f} (esperado 1.0 +/- 0.01)"] if not passed else [f"suma={total:.4f}"],
    )


def gate_bear_le_base_le_bull(case: dict) -> dict:
    """The bear case is not above the base case, and the base is not above the bull.

    A DCF whose scenarios are inverted still produces a plausible-looking
    expected value, because most consumers only read that one number.
    """
    artifact = _artifact(case)
    gate = "bear_le_base_le_bull"
    bear = _as_float(artifact.get("bear_value"))
    base = _as_float(artifact.get("base_value"))
    bull = _as_float(artifact.get("bull_value"))
    present = [value for value in (bear, base, bull) if value is not None]
    if not present:
        if artifact.get("status") == "ok":
            return _result(gate, False, ["status=ok sin ningun escenario valorable"])
        return _result(gate, True, ["celda de abstención: no aplica"])
    if len(present) != 3:
        return _result(
            gate,
            False,
            [f"escenarios incompletos: bear={bear} base={base} bull={bull}"],
        )
    problems: list[str] = []
    if bear > base:
        problems.append(f"bear {bear} > base {base}")
    if base > bull:
        problems.append(f"base {base} > bull {bull}")
    if bear > bull:
        problems.append(f"bear {bear} > bull {bull}")
    return _result(gate, not problems, problems)


def gate_degraded_reason_present_when_degraded(case: dict) -> dict:
    """``degraded`` and ``degraded_reason`` always agree.

    A cell flagged degraded with no reason cannot be triaged, and a cell that is
    quietly degraded with a blank reason is how a run ends up reporting a 0%
    degradation rate over data that was never publishable.
    """
    artifact = _artifact(case)
    gate = "degraded_reason_present_when_degraded"
    degraded = artifact.get("degraded")
    reason = (artifact.get("degraded_reason") or "").strip()
    if degraded is None:
        return _result(gate, False, ["la celda no declara 'degraded'"])
    if degraded and not reason:
        return _result(gate, False, ["degraded=true sin degraded_reason"])
    if not degraded and reason:
        return _result(gate, False, [f"degraded=false pero con motivo {reason!r}"])
    if degraded and len(reason) < 8:
        return _result(gate, False, [f"degraded_reason demasiado vago: {reason!r}"])
    return _result(gate, True, [reason] if reason else [])


def gate_claims_have_evidence_ratio_recorded(case: dict) -> dict:
    """Both claim counts exist and the numerator cannot exceed the denominator.

    Recording only the numerator is how "100% of claims have evidence" gets
    printed over a cell that had no claims at all.
    """
    artifact = _artifact(case)
    gate = "claims_have_evidence_ratio_recorded"
    total = artifact.get("n_claims")
    with_evidence = artifact.get("n_claims_with_evidence")
    if total is None or with_evidence is None:
        return _result(
            gate,
            False,
            ["la celda no declara n_claims / n_claims_with_evidence"],
        )
    if not isinstance(total, int) or not isinstance(with_evidence, int):
        return _result(
            gate,
            False,
            [f"conteos no enteros: n_claims={total!r} n_claims_with_evidence={with_evidence!r}"],
        )
    problems: list[str] = []
    if total < 0 or with_evidence < 0:
        problems.append(f"conteos negativos: {total} / {with_evidence}")
    if with_evidence > total:
        problems.append(
            f"n_claims_with_evidence {with_evidence} > n_claims {total}: ratio imposible"
        )
    if artifact.get("status") == "ok" and total == 0:
        problems.append("status=ok sin ninguna claim que auditar")
    return _result(gate, not problems, problems)


def gate_net_neutral_honest(case: dict) -> dict:
    """A ticker cannot produce the same fair value on every date for no reason.

    The signature of a backtest with no real information: the snapshot is
    rebuilt from the same last fact each time, so every cutoff yields the same
    number and the "track record" is a horizontal line. A constant is allowed
    when the case declares why — one month of filings, a static balance sheet —
    and never otherwise.
    """
    artifact = _artifact(case)
    gate = "net_neutral_honest"
    siblings = artifact.get("siblings") or []
    if len(siblings) < 2:
        return _result(gate, True, ["menos de dos fechas: no aplica"])
    values = [
        _as_float(item.get("fair_value"))
        for item in siblings
        if item.get("status", "ok") == "ok"
    ]
    values = [value for value in values if value is not None]
    if len(values) < 2:
        return _result(gate, True, ["menos de dos celdas validas: no aplica"])
    distinct = {round(value, 6) for value in values}
    if len(distinct) == 1:
        reason = (artifact.get("declared_constant_reason") or "").strip()
        if not reason:
            return _result(
                gate,
                False,
                [
                    f"las {len(values)} celdas dan el mismo fair_value "
                    f"{values[0]} sin motivo declarado"
                ],
            )
        return _result(gate, True, [f"constante declarado: {reason}"])
    return _result(gate, True, [f"{len(distinct)} fair values distintos entre {len(values)} celdas"])


GATES = {
    "no_lookahead": gate_no_lookahead,
    "evidence_cutoff_respected": gate_evidence_cutoff_respected,
    "insufficient_data_not_filled_with_price": gate_insufficient_data_not_filled_with_price,
    "probabilities_sum_to_one": gate_probabilities_sum_to_one,
    "bear_le_base_le_bull": gate_bear_le_base_le_bull,
    "degraded_reason_present_when_degraded": gate_degraded_reason_present_when_degraded,
    "source_coverage_score_present": gate_source_coverage_score_present,
    "claims_have_evidence_ratio_recorded": gate_claims_have_evidence_ratio_recorded,
    "no_invented_numbers": gate_no_invented_numbers,
    "idempotent_replay": gate_idempotent_replay,
    "net_neutral_honest": gate_net_neutral_honest,
}

#: Gates that must FAIL (never pass, never skip) when the key they verify is
#: missing. Each one is a "no aplica" that would otherwise hide a broken audit.
NON_SKIPPABLE_GATES = (
    "no_lookahead",
    "evidence_cutoff_respected",
    "no_invented_numbers",
    "idempotent_replay",
    "source_coverage_score_present",
)

MISSING_KEY_MESSAGES = {
    "no_lookahead": "falta expected.as_of: el gate no puede omitirse",
    "evidence_cutoff_respected": (
        "falta expected.evidence_cutoff: el gate no puede omitirse"
    ),
    "no_invented_numbers": "el caso no declara frozen_facts: el gate no puede omitirse",
    "idempotent_replay": (
        "faltan replay_hash / replay_hash_again: el gate no puede omitirse"
    ),
    "source_coverage_score_present": (
        "la celda no declara source_coverage_score: el gate no puede omitirse"
    ),
}


def run_case(case: dict) -> list[dict]:
    return [gate(case) for gate in GATES.values()]


__all__ = [
    "GATES",
    "MISSING_KEY_MESSAGES",
    "NON_SKIPPABLE_GATES",
    "run_case",
]
