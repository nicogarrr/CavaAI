"""D3: hard gates deterministas sobre el retorno realizado de una tesis.

Mismo contrato que ``evals/gates.py``: cada gate es una función pura sobre el
caso, devuelve ``{"gate", "passed", "details"}`` y no sabe nada de la base de
datos. Lo que se evalúa es el artefacto (la foto tesis ↔ mercado serializada)
contra los ``frozen_facts`` del caso: los precios y la cotización que sí
existían.

Los tres gates marcados aquí como NO OMITIBLES no se pueden silenciar con un
``applies_to`` que no los mencione, y fallan fuerte cuando su entrada falta: un
gate que se apaga justo cuando falta el dato es un gate que no vigila nada.
"""

from __future__ import annotations

import re

from evals.gates import _norm_number

OUTCOMES = ("thesis_right", "thesis_wrong", "inconclusive", "too_early")
COUNTABLE = ("thesis_right", "thesis_wrong")

#: Gates que el runner ejecuta siempre, ignorando el opt-out del caso.
NON_SKIPPABLE_GATES = frozenset(
    {"outcome_deterministico", "no_lookahead_entry", "missing_price_is_not_zero"}
)

_NUMBER_RE = re.compile(r"-?\d[\d.,]*")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
#: Índices, ordinales y signos de dirección: no son hechos financieros.
_TOLERANCE_VALUES = frozenset(range(-5, 6))
#: Porcentajes con signo tal y como los escribe el servicio en es-ES.
_PROSE_FIELDS = ("verdict_reason", "entry_price_rule")
_HORIZON_PROSE_FIELDS = ("reason", "alpha_reason", "excursion_reason", "base_reason")


def _result(gate: str, passed: bool, details: list[str]) -> dict:
    return {"gate": gate, "passed": passed, "details": details}


def _artifact(case: dict) -> dict:
    return case.get("artifact") or {}


def _expected(case: dict) -> dict:
    return case.get("expected") or {}


def _horizons(artifact: dict) -> list[dict]:
    rows = artifact.get("horizons") or []
    return [row for row in rows if isinstance(row, dict)]


def _num(value: object) -> float | None:
    if value is None:
        return None
    return _norm_number(str(value))


def gate_outcome_deterministico(case: dict) -> dict:
    """El veredicto es el declarado, y el declarado es una de las 4 clases."""
    artifact = _artifact(case)
    actual = artifact.get("outcome")
    expected = _expected(case).get("outcome")
    if expected is None:
        return _result(
            "outcome_deterministico",
            False,
            [
                "el caso no declara expected.outcome: el gate no puede omitirse "
                "(sin el veredicto esperado cualquiera pasa)"
            ],
        )
    if actual not in OUTCOMES:
        return _result(
            "outcome_deterministico",
            False,
            [f"outcome {actual!r} no es una de las {len(OUTCOMES)} clases declaradas"],
        )
    if actual != expected:
        return _result(
            "outcome_deterministico",
            False,
            [f"outcome {actual!r} != esperado {expected!r}"],
        )
    countable = actual in COUNTABLE
    if bool(artifact.get("counts_toward_hit_rate")) != countable:
        return _result(
            "outcome_deterministico",
            False,
            [
                f"counts_toward_hit_rate {artifact.get('counts_toward_hit_rate')} "
                f"contradice el outcome {actual!r} (solo {COUNTABLE} cuentan)"
            ],
        )
    return _result("outcome_deterministico", True, [f"outcome={actual}"])


def gate_no_lookahead_entry(case: dict) -> dict:
    """Entrada nunca anterior a la publicación, salida nunca anterior a la entrada."""
    artifact = _artifact(case)
    published = artifact.get("thesis_published_at")
    entry_date = artifact.get("entry_date")
    problems: list[str] = []
    if not published:
        return _result(
            "no_lookahead_entry",
            False,
            ["el artefacto no trae thesis_published_at: el gate no puede omitirse"],
        )
    if entry_date is not None and str(entry_date) < str(published)[:10]:
        problems.append(
            f"entry_date {entry_date} es anterior a la publicación {str(published)[:10]}: "
            "look-ahead"
        )
    status = artifact.get("entry_price_status")
    if status not in {"exact", "next_session", "missing", "spot_only", "no_series"}:
        problems.append(f"entry_price_status {status!r} desconocido")
    if entry_date is not None and status not in {"exact", "next_session"}:
        problems.append(f"hay entry_date pero el estado del precio de entrada es {status!r}")
    for item in _horizons(artifact):
        exit_date = item.get("exit_date")
        if exit_date is None or entry_date is None:
            continue
        if str(exit_date) < str(entry_date):
            problems.append(
                f"horizonte {item.get('horizon')}: exit_date {exit_date} anterior a la "
                f"entrada {entry_date}"
            )
    return _result("no_lookahead_entry", not problems, problems)


def gate_missing_price_is_not_zero(case: dict) -> dict:
    """Un horizonte sin precio no vale 0: vale N/D, y con motivo."""
    artifact = _artifact(case)
    problems: list[str] = []
    entry_date = artifact.get("entry_date")
    horizons = _horizons(artifact)
    if not horizons:
        return _result(
            "missing_price_is_not_zero",
            False,
            ["el artefacto no trae horizontes: el gate no puede omitirse"],
        )
    if entry_date is None:
        for item in horizons:
            if item.get("realized_return") is not None:
                problems.append(
                    f"horizonte {item.get('horizon')}: sin precio de entrada pero con "
                    f"realized_return {item.get('realized_return')!r}"
                )
            if not item.get("reason"):
                problems.append(f"horizonte {item.get('horizon')}: N/D sin motivo")
    for item in horizons:
        measured = item.get("status") == "ok"
        value = _num(item.get("realized_return"))
        if not measured:
            if item.get("realized_return") is not None:
                problems.append(
                    f"horizonte {item.get('horizon')} con estado "
                    f"{item.get('status')!r} trae realized_return "
                    f"{item.get('realized_return')!r} en vez de N/D"
                )
            if value == 0:
                problems.append(
                    f"horizonte {item.get('horizon')} sin precio reported como 0 %"
                )
            if not item.get("reason"):
                problems.append(f"horizonte {item.get('horizon')}: N/D sin motivo")
        elif value is None:
            problems.append(
                f"horizonte {item.get('horizon')} marcado ok sin realized_return numérico"
            )
    return _result("missing_price_is_not_zero", not problems, problems)


def gate_benchmark_required_for_alpha(case: dict) -> dict:
    """Sin benchmark no hay alfa: N/D con motivo, jamás 0 = sin alfa."""
    artifact = _artifact(case)
    problems: list[str] = []
    benchmark_status = artifact.get("benchmark_status")
    for item in _horizons(artifact):
        alpha_raw = item.get("alpha")
        alpha = _num(alpha_raw)
        if alpha_raw is not None and alpha is None:
            problems.append(
                f"horizonte {item.get('horizon')}: alpha {alpha_raw!r} no es un número"
            )
        if alpha == 0 and not item.get("benchmark_return"):
            problems.append(
                f"horizonte {item.get('horizon')}: alfa 0 con benchmark ausente "
                f"(estado {benchmark_status!r}); 0 = sin alfa es propaganda"
            )
        # En un horizonte no medido el alfa ya viene explicado por `reason`; el
        # motivo propio del alfa sólo se exige cuando el retorno sí se midió.
        if (
            alpha_raw is None
            and item.get("alpha_reason") is None
            and item.get("status") == "ok"
        ):
            problems.append(
                f"horizonte {item.get('horizon')}: alfa N/D sin motivo declarado"
            )
    return _result("benchmark_required_for_alpha", not problems, problems)


def _judgement_horizon(artifact: dict) -> dict | None:
    """El horizonte de juicio: el declarado como `holding_horizon_days`."""
    wanted = _num(artifact.get("holding_horizon_days"))
    for item in _horizons(artifact):
        if _num(item.get("horizon_days")) == wanted:
            return item
    return None


def gate_outcome_reason_present(case: dict) -> dict:
    """Un veredicto sin motivo no es auditable, y `too_early` se apoya en su horizonte."""
    artifact = _artifact(case)
    outcome = artifact.get("outcome")
    reason = artifact.get("verdict_reason")
    problems: list[str] = []
    if not reason or not str(reason).strip():
        problems.append(f"outcome {outcome!r} sin verdict_reason")
    if outcome == "too_early":
        judgement = _judgement_horizon(artifact)
        if judgement is None:
            problems.append("outcome too_early sin horizonte de juicio en el artefacto")
        elif judgement.get("status") != "too_early":
            problems.append(
                f"too_early con el horizonte de juicio en estado "
                f"{judgement.get('status')!r}: no es demasiado pronto"
            )
        if artifact.get("judgement_status") != "too_early":
            problems.append(
                f"judgement_status {artifact.get('judgement_status')!r} no es too_early"
            )
    return _result("outcome_reason_present", not problems, problems)


def gate_drawdown_sign_consistent(case: dict) -> dict:
    """El drawdown nunca es positivo y el retorno cae dentro de lo que el camino recorrió."""
    artifact = _artifact(case)
    problems: list[str] = []
    for item in _horizons(artifact):
        label = item.get("horizon")
        drawdown = _num(item.get("max_drawdown"))
        run_up = _num(item.get("max_run_up"))
        realized = _num(item.get("realized_return"))
        if drawdown is not None and drawdown > 0:
            problems.append(f"{label}: max_drawdown {drawdown} positivo (una caída no sube)")
        if drawdown is not None and drawdown < -1:
            problems.append(f"{label}: max_drawdown {drawdown} por debajo de -100 %")
        if run_up is not None and run_up < 0:
            problems.append(f"{label}: max_run_up {run_up} negativo (una subida no baja)")
        if realized is None:
            continue
        if drawdown is not None and realized < drawdown:
            problems.append(
                f"{label}: retorno {realized} por debajo del max_drawdown {drawdown}; el "
                "camino recorrido no puede acabar donde no estuvo"
            )
        if run_up is not None and realized > run_up:
            problems.append(
                f"{label}: retorno {realized} por encima del max_run_up {run_up}; el "
                "camino recorrido no puede acabar donde no estuvo"
            )
    return _result("drawdown_sign_consistent", not problems, problems)


def gate_horizons_monotonic_in_time(case: dict) -> dict:
    """1M ≤ 3M ≤ 6M ≤ 1A ≤ 2A en días y en fecha de salida."""
    artifact = _artifact(case)
    problems: list[str] = []
    rows = _horizons(artifact)
    ordered = sorted(rows, key=lambda row: _num(row.get("horizon_days")) or 0)
    if [row.get("horizon") for row in rows] != [row.get("horizon") for row in ordered]:
        problems.append("los horizontes no vienen ordenados por longitud")
    previous_days: float | None = None
    previous_exit: str | None = None
    for row in ordered:
        days = _num(row.get("horizon_days"))
        if days is None:
            problems.append(f"horizonte {row.get('horizon')!r} sin horizon_days")
            continue
        if previous_days is not None and days <= previous_days:
            problems.append(
                f"horizonte_days {days} no crece respecto al anterior {previous_days}"
            )
        previous_days = days
        exit_date = row.get("exit_date")
        if exit_date is None:
            continue
        if previous_exit is not None and str(exit_date) < previous_exit:
            problems.append(
                f"horizonte {row.get('horizon')}: exit_date {exit_date} anterior al del "
                f"horizonte corto ({previous_exit})"
            )
        previous_exit = str(exit_date)
    return _result("horizons_monotonic_in_time", not problems, problems)


def gate_currency_declared_or_null(case: dict) -> dict:
    """Moneda declarada de 3 letras ISO, o N/D con motivo: nunca una inventada."""
    artifact = _artifact(case)
    currency = artifact.get("currency")
    problems: list[str] = []
    if currency is not None:
        code = str(currency).strip()
        if len(code) != 3 or not code.isalpha() or code != code.upper():
            problems.append(f"divisa {currency!r} no es un código ISO de tres letras")
    for item in _horizons(artifact):
        base_raw = item.get("realized_return_base")
        if base_raw is None and not (item.get("base_reason") or item.get("reason")):
            problems.append(
                f"horizonte {item.get('horizon')}: retorno en moneda base N/D sin motivo"
            )
        if currency is None and base_raw is not None:
            problems.append(
                f"horizonte {item.get('horizon')}: retorno en moneda base "
                f"{base_raw!r} sin que la compañía declare divisa"
            )
        if item.get("currency") is not None and item.get("currency") != currency:
            problems.append(
                f"horizonte {item.get('horizon')}: moneda {item.get('currency')!r} distinta "
                f"de la declarada {currency!r}"
            )
    return _result("currency_declared_or_null", not problems, problems)


def gate_no_invented_numbers(case: dict) -> dict:
    """Cada número del veredicto tiene que estar en los hechos congelados.

    Reutiliza ``evals.gates._norm_number`` (coma decimal española incluida): las
    fechas ISO se descartan antes de escanear porque ``2026-01-15`` no es una
    cifra financiera.
    """
    artifact = _artifact(case)
    frozen = {
        value
        for value in (_num(item) for item in (case.get("frozen_facts") or {}).values())
        if value is not None
    }
    if not frozen:
        return _result(
            "no_invented_numbers",
            False,
            ["el caso no trae frozen_facts: ningún número del artefacto puede justificarse"],
        )
    problems: list[str] = []
    texts: list[tuple[str, str]] = [
        (field, str(artifact.get(field) or "")) for field in _PROSE_FIELDS
    ]
    for item in _horizons(artifact):
        for field in _HORIZON_PROSE_FIELDS:
            texts.append((f"{item.get('horizon')}.{field}", str(item.get(field) or "")))
    for field, text in texts:
        cleaned = _ISO_DATE_RE.sub(" ", text)
        for match in _NUMBER_RE.findall(cleaned):
            number = _num(match)
            if number is None or number in _TOLERANCE_VALUES:
                continue
            if number not in frozen:
                problems.append(f"numero sin frozen fact en {field}: {match}")
    return _result("no_invented_numbers", not problems, problems[:10])


def gate_idempotent_recompute(case: dict) -> dict:
    """Recalcular sin precios nuevos no crea revisión; con precios nuevos, sí."""
    artifact = _artifact(case)
    expected = _expected(case)
    revisions = artifact.get("revision") or 1
    fingerprint = artifact.get("price_fingerprint")
    history = artifact.get("revisions") or []
    problems: list[str] = []
    if not fingerprint:
        return _result(
            "idempotent_recompute",
            False,
            ["el artefacto no trae price_fingerprint: el gate no puede omitirse"],
        )
    prices_changed = expected.get("prices_changed")
    if prices_changed is True:
        if revisions < 2:
            problems.append(
                f"los precios cambiaron pero la revisión sigue en {revisions}: la "
                "corrección no se guardó"
            )
        if len(history) < revisions:
            problems.append(
                f"revision={revisions} pero sólo {len(history)} revisiones registradas"
            )
    elif prices_changed is False:
        if revisions != 1:
            problems.append(
                f"los precios no cambiaron y aun así hay {revisions} revisiones"
            )
    if len(history) > len({row.get("price_fingerprint") for row in history}):
        problems.append("el historial de revisiones repite price_fingerprint")
    return _result("idempotent_recompute", not problems, problems)


def gate_too_early_not_counted_as_wrong(case: dict) -> dict:
    """`too_early` no es un fallo, y `thesis_wrong` necesita un retorno medido."""
    artifact = _artifact(case)
    outcome = artifact.get("outcome")
    problems: list[str] = []
    if outcome == "too_early":
        if artifact.get("counts_toward_hit_rate"):
            problems.append("too_early cuenta para el hit-rate: un acierto futuro no es un acierto")
        judgement = _judgement_horizon(artifact)
        if judgement is None or judgement.get("status") != "too_early":
            problems.append(
                "too_early con el horizonte de juicio ya medido: no es demasiado pronto"
            )
    if outcome == "thesis_wrong":
        judgement = _judgement_horizon(artifact)
        if judgement is None or judgement.get("status") != "ok":
            problems.append(
                "thesis_wrong sin horizonte de juicio medido: un veredicto de fallo "
                "exige el retorno de salida"
            )
        else:
            direction = _num(artifact.get("direction"))
            if direction is None:
                problems.append("thesis_wrong sin dirección declarada: no se puede comprobar")
            else:
                signed = (_num(judgement.get("realized_return")) or 0) * direction
                if signed > 0:
                    problems.append(
                        f"thesis_wrong con retorno firmado {signed} a favor de la tesis"
                    )
    return _result("too_early_not_counted_as_wrong", not problems, problems)


GATES = {
    "outcome_deterministico": gate_outcome_deterministico,
    "no_lookahead_entry": gate_no_lookahead_entry,
    "missing_price_is_not_zero": gate_missing_price_is_not_zero,
    "benchmark_required_for_alpha": gate_benchmark_required_for_alpha,
    "outcome_reason_present": gate_outcome_reason_present,
    "drawdown_sign_consistent": gate_drawdown_sign_consistent,
    "horizons_monotonic_in_time": gate_horizons_monotonic_in_time,
    "currency_declared_or_null": gate_currency_declared_or_null,
    "no_invented_numbers": gate_no_invented_numbers,
    "idempotent_recompute": gate_idempotent_recompute,
    "too_early_not_counted_as_wrong": gate_too_early_not_counted_as_wrong,
}


def run_case(case: dict) -> list[dict]:
    return [gate(case) for gate in GATES.values()]
