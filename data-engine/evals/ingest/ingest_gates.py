"""C4: hard gates deterministas de PRECISION de la ingesta.

Mismo contrato que `evals/gates.py`: cada gate es una funcion pura
``f(case) -> {"gate", "passed", "details"}`` sobre el caso del dataset y la
observacion que el harness produjo (``case["observed"]``). Nada de LLM juzgando a
LLM: numeros contra los valores declarados en el fixture, periodos contra la
etiqueta que el fixture declara, procedencia contra la verificacion real del
indice SEC y abstention contra los campos que el fixture declara ausentes.

Tres puertas NO se pueden omitir. Omitir la clave silenciaba justo la puerta que
existe para detectar esa omision:

- ``no_lookahead``: sin ``expected.as_of`` no hay contra que comparar, asi que el
  caso no se puede puntuar. Falla con "el gate no puede omitirse".
- ``official_only_if_index_verified``: sin ``expected.index`` no hay lista de
  accessions verificadas, y sin ella cualquier hecho podria declararse OFICIAL.
- ``absent_fields_reported_as_null``: sin ``expected.absent_metrics`` no hay campo
  alguno cuya fabricacion se pueda detectar.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

FAMILY_SOURCE_TYPES = {
    # primary_official: un filing SEC verificado contra su indice (regla de oro).
    "sec": ("SEC", "FMP_profile", "primary_official"),
    "fmp": ("FMP", "FMP_profile"),
    "esef": ("ESEF",),
}

NON_SKIPPABLE_GATES = (
    "no_lookahead",
    "official_only_if_index_verified",
    "absent_fields_reported_as_null",
)

MIN_CASES = 60
MIN_NEGATIVE_CONTROLS = 8
MIN_DEGRADATION_CASES = 5
MIN_FAMILY_CASES = 12
MIN_SEC_CASES = 25


# --------------------------------------------------------------------------
# Utilidades puras
# --------------------------------------------------------------------------


def _result(gate: str, passed: bool, details: list[str]) -> dict:
    return {"gate": gate, "passed": passed, "details": details}


def _omitted(gate: str, key: str, why: str) -> dict:
    return _result(
        gate, False, [f"falta expected.{key}: el gate no puede omitirse ({why})"]
    )


def _observed_facts(case: dict) -> list[dict]:
    """Hechos financials persistidos (los del conector se leen aparte)."""
    return [
        fact
        for fact in (case.get("observed") or {}).get("facts") or []
        if "metric" in fact
    ]


def _expected_facts(case: dict) -> list[dict]:
    return list((case.get("expected") or {}).get("facts") or [])


def _facts_by_key(observed: list[dict]) -> dict[tuple[str, str], list[dict]]:
    index: dict[tuple[str, str], list[dict]] = {}
    for fact in observed:
        index.setdefault((fact["metric"], fact["period"]), []).append(fact)
    return index


def _period_date(period: Any) -> tuple[str | None, str | None]:
    """(fecha ISO, problema) que la etiqueta de periodo declara.

    '<end>:FY' / '<end>:Q1' / '<end>:TTM'. Una etiqueta NO PARSEABLE no es
    "sin fecha": es un defecto de la etiqueta (`2025-99-99:FY`,
    `1767225600:FY`) y se devuelve como problema para que la puerta lo acuse.
    Solo esta funcion (compartida con el runner) decide que es una fecha de
    periodo: dos implementaciones divergentes dejaban pasar etiquetas
    imposibles por una via y las cazaban por otra (FIX5-10).
    """
    if not isinstance(period, str) or ":" not in period:
        return None, None
    head = period.split(":", 1)[0]
    try:
        return date.fromisoformat(head).isoformat(), None
    except ValueError:
        return None, f"etiqueta de periodo no parseable: {period!r}"


def _tolerance(case: dict) -> tuple[Decimal, Decimal]:
    tolerance = (case.get("expected") or {}).get("tolerance") or {}
    try:
        relative = Decimal(str(tolerance.get("relative", "0")))
        absolute = Decimal(str(tolerance.get("absolute", "0")))
    except InvalidOperation:
        return Decimal("0"), Decimal("0")
    return relative, absolute


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _matches(actual: Any, expected: Any, tolerance: tuple[Decimal, Decimal]) -> bool:
    left = _as_decimal(actual)
    right = _as_decimal(expected)
    if left is None or right is None:
        return actual == expected
    relative, absolute = tolerance
    return abs(left - right) <= max(absolute, relative * abs(right))


def _fact_value(row: dict, expected: Any, tolerance: tuple[Decimal, Decimal]) -> bool:
    return _matches(row.get("value"), expected, tolerance)


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------


def gate_fixture_schema_valid(case: dict) -> dict:
    """El caso declara su forma y todos sus fixtures son sinteticos declarados."""
    import json

    from evals.ingest.harness import declared_fixtures, fixture_path

    problems: list[str] = []
    for key in ("id", "family", "scenario", "expected"):
        if not case.get(key):
            problems.append(f"falta {key}")
    family = case.get("family")
    if family and family not in FAMILY_SOURCE_TYPES:
        problems.append(f"familia de fuente desconocida: {family}")
    expected = case.get("expected") or {}
    tolerance = expected.get("tolerance")
    if not isinstance(tolerance, dict):
        problems.append("expected.tolerance ausente: la tolerancia debe declararse")
    else:
        for key in ("relative", "absolute"):
            if _as_decimal(tolerance.get(key)) is None:
                problems.append(f"expected.tolerance.{key} no es numero")
    for fact in _expected_facts(case):
        for key in ("metric", "period", "unit"):
            if not isinstance(fact.get(key), str) or not fact[key]:
                problems.append(f"expected.facts: {key} ausente o no texto")
        if _as_decimal(fact.get("value")) is None:
            problems.append(f"expected.facts[{fact.get('metric')}]: value no numerico")
    for relative in declared_fixtures(case):
        try:
            path = fixture_path(relative)
        except FileNotFoundError as exc:
            problems.append(str(exc))
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            payload = json.loads(text)
            if isinstance(payload, dict) and payload.get("origin") != "synthetic_fixture":
                problems.append(f"{relative} no declara origin=synthetic_fixture")
        elif "synthetic_fixture" not in text:
            problems.append(f"{relative} no declara origin=synthetic_fixture")
    return _result("fixture_schema_valid", not problems, problems[:10])


def gate_extracted_values_match_fixture(case: dict) -> dict:
    """Cada campo numerico declarado aparece con el valor que el fixture declara.

    Cubre tambien lo que el conector devuelve antes de la BD: los conceptos que
    sobrevivieron a `normalize_xbrl_json` (`expected.normalized_facts`) y los
    parametros con los que se pidio cada endpoint (`expected.requests`). Son
    valores extraidos de la fuente, no metadatos de la corrida.

    Un periodo con DOS valores distintos (dos filas del proveedor, dos tags que
    no se colapsaron) es un fallo aunque uno de ellos sea el declarado: el
    pipeline publico una cifra ambigua.
    """
    expected = case.get("expected") or {}
    expected_facts = _expected_facts(case)
    nothing_expected = bool(expected.get("extracts_nothing"))
    if not expected_facts and not nothing_expected and not expected.get("normalized_facts") \
            and not expected.get("requests"):
        return _result(
            "extracted_values_match_fixture",
            False,
            [
                "el caso no declara expected.facts ni expected.extracts_nothing: "
                "el gate no puede omitirse"
            ],
        )
    observed = _observed_facts(case)
    index = _facts_by_key(observed)
    tolerance = _tolerance(case)
    problems: list[str] = []
    matched = 0
    for fact in expected_facts:
        rows = index.get((fact["metric"], fact["period"])) or []
        if not rows:
            problems.append(f"ausente {fact['metric']}@{fact['period']}")
            continue
        winners = [row for row in rows if _fact_value(row, fact["value"], tolerance)]
        losers = [row for row in rows if not _fact_value(row, fact["value"], tolerance)]
        if losers:
            got = ", ".join(f"{row.get('value')} ({row.get('source_type')})" for row in rows)
            reason = "cifra ambigua en el periodo" if winners else "no es el valor declarado"
            problems.append(
                f"{fact['metric']}@{fact['period']}: {got} -> {reason} "
                f"{fact['value']}"
            )
            continue
        row = winners[0]
        if "is_reported" in fact and row["is_reported"] != fact["is_reported"]:
            problems.append(
                f"{fact['metric']}@{fact['period']}: is_reported={row['is_reported']} "
                f"!= declarado {fact['is_reported']}"
            )
            continue
        matched += 1
    if nothing_expected and any("metric" in row for row in observed):
        problems.append(
            f"el caso declara extracts_nothing pero la ingesta publico "
            f"{sum(1 for row in observed if 'metric' in row)} hechos"
        )
    problems.extend(_normalized_problems(case))
    problems.extend(_request_problems(case))
    total = (
        len(expected_facts)
        + len(expected.get("normalized_facts") or [])
        + len(expected.get("requests") or [])
        + (1 if nothing_expected else 0)
    )
    return _result(
        "extracted_values_match_fixture",
        not problems,
        [f"{matched}/{total} valores extraidos con lo declarado", *problems[:10]],
    )


def _normalized_problems(case: dict) -> list[str]:
    expected = (case.get("expected") or {}).get("normalized_facts")
    if not expected:
        return []
    seen = {
        (row.get("concept"), row.get("unit")): row.get("entries")
        for row in (case.get("observed") or {}).get("facts") or []
        if "concept" in row
    }
    problems = []
    for row in expected:
        key = (row.get("concept"), row.get("unit"))
        if key not in seen:
            problems.append(f"concepto no extraido del render: {key}")
        elif seen[key] != row.get("entries"):
            problems.append(f"{key}: {seen[key]} entradas != declaradas {row.get('entries')}")
    return problems


def _request_problems(case: dict) -> list[str]:
    expected = (case.get("expected") or {}).get("requests")
    if not expected:
        return []
    observed = (case.get("observed") or {}).get("requests") or []
    problems = []
    for row in expected:
        found = next((r for r in observed if r.get("path") == row.get("path")), None)
        if found is None:
            problems.append(f"endpoint no solicitado: {row.get('path')}")
            continue
        for key, value in (row.get("params") or {}).items():
            if str(found.get("params", {}).get(key)) != str(value):
                problems.append(
                    f"{row['path']}: {key}={found.get('params', {}).get(key)!r} != {value!r}"
                )
    return problems


def gate_period_attribution_correct(case: dict) -> dict:
    """El hecho cae en el periodo declarado: etiqueta, ejercicio y trimestre.

    Un hecho declarado que NO aparece cuenta como fallo: no se atribuyo a ningun
    periodo, que es exactamente el modo de fallo que mide esta puerta.
    """
    expected = case.get("expected") or {}
    expected_facts = _expected_facts(case)
    if not expected_facts and not expected.get("statements") \
            and not expected.get("periods") and not expected.get("extracts_nothing"):
        return _result(
            "period_attribution_correct",
            False,
            [
                "el caso no declara expected.facts ni expected.periods: "
                "el gate no puede omitirse"
            ],
        )
    observed = _observed_facts(case)
    index = _facts_by_key(observed)
    tolerance = _tolerance(case)
    problems: list[str] = []
    correct = 0
    for fact in expected_facts:
        rows = index.get((fact["metric"], fact["period"])) or []
        if not rows:
            problems.append(
                f"{fact['metric']} no se atribuyo al periodo declarado {fact['period']}"
            )
            continue
        row = next((r for r in rows if _fact_value(r, fact["value"], tolerance)), rows[0])
        declared_year = fact.get("fiscal_year", row["fiscal_year"])
        declared_quarter = fact.get("fiscal_quarter", row["fiscal_quarter"])
        if (row["fiscal_year"], row["fiscal_quarter"]) == (declared_year, declared_quarter):
            correct += 1
        else:
            problems.append(
                f"{fact['metric']}@{fact['period']} fy={row['fiscal_year']}/"
                f"fq={row['fiscal_quarter']} != {declared_year}/{declared_quarter}"
            )
    for metric, periods in sorted((expected.get("periods") or {}).items()):
        seen = sorted({fact["period"] for fact in observed if fact["metric"] == metric})
        if sorted(periods) != seen:
            problems.append(f"{metric}: periodos {seen} != declarados {sorted(periods)}")
    for declared in expected.get("statements") or []:
        found = next(
            (
                row
                for row in (case.get("observed") or {}).get("statements") or []
                if row["statement_type"] == declared.get("statement_type")
                and row["period"] == declared.get("period")
            ),
            None,
        )
        if found is None:
            problems.append(
                f"declaracion {declared.get('statement_type')} ausente en "
                f"{declared.get('period')}"
            )
        elif (found["fiscal_year"], found["fiscal_quarter"]) != (
            declared.get("fiscal_year"),
            declared.get("fiscal_quarter"),
        ):
            problems.append(
                f"declaracion {declared.get('statement_type')} "
                f"{declared.get('period')}: fy={found['fiscal_year']}/"
                f"fq={found['fiscal_quarter']} != "
                f"{declared.get('fiscal_year')}/{declared.get('fiscal_quarter')}"
            )
        else:
            correct += 1
    total = len(expected_facts) + len(expected.get("statements") or [])
    return _result(
        "period_attribution_correct",
        not problems,
        [f"{correct}/{total} periodos atribuidos al declarado", *problems[:10]],
    )


def gate_no_lookahead(case: dict) -> dict:
    """Ningun hecho de un periodo posterior a `expected.as_of` puede publicarse."""
    as_of = (case.get("expected") or {}).get("as_of")
    if not isinstance(as_of, str) or len(as_of) < 10:
        return _omitted(
            "no_lookahead",
            "as_of",
            "sin fecha de corte un hecho de FY2999 seria indistinguible de uno vigente",
        )
    try:
        cutoff = date.fromisoformat(as_of[:10])
    except ValueError:
        return _result("no_lookahead", False, [f"expected.as_of no es fecha: {as_of!r}"])
    problems: list[str] = []
    for fact in _observed_facts(case):
        period_date, problem = _period_date(fact["period"])
        if problem:
            # Un periodo sin fecha legible no se puede acotar: se acusa, no se
            # salta el filtro (FIX5-10).
            problems.append(f"{fact['metric']}@{fact['period']}: {problem}")
            continue
        if period_date and date.fromisoformat(period_date) > cutoff:
            problems.append(
                f"look-ahead: {fact['metric']}@{fact['period']} es posterior a {as_of}"
            )
    forbidden = (case.get("expected") or {}).get("forbidden_values") or []
    if forbidden:
        seen = {_as_decimal(fact.get("value")) for fact in _observed_facts(case)}
        for value in forbidden:
            if _as_decimal(value) in seen:
                problems.append(f"valor de look-ahead presente en la ingesta: {value}")
    return _result("no_lookahead", not problems, problems[:10] or [f"as_of={as_of} respetado"])


def gate_official_only_if_index_verified(case: dict) -> dict:
    """OFICIAL exige indice verificado; lo no verificado NUNCA puede ser OFICIAL."""
    index = (case.get("expected") or {}).get("index")
    if not isinstance(index, dict) or "verified" not in index:
        return _omitted(
            "official_only_if_index_verified",
            "index",
            "sin lista de accessions verificadas cualquier hecho podria declararse OFICIAL",
        )
    verified = list(index.get("verified") or [])
    official = list(index.get("official") or [])
    unverified = list(index.get("unverified") or [])
    provenance = (case.get("observed") or {}).get("provenance") or {}
    index_verification = (case.get("observed") or {}).get("index_verification") or {}
    problems: list[str] = []

    for accession in verified:
        record = index_verification.get(accession)
        if record is None:
            problems.append(f"accession {accession} nunca se evaluo contra su indice")
        elif not record.get("verified"):
            problems.append(
                f"accession {accession} declarado verificado pero el indice lo rechazo "
                f"({record.get('reason') or record.get('status')})"
            )
    for accession in official:
        if accession not in verified:
            problems.append(f"accession {accession} se declara OFICIAL sin estar verificado")
        cited = [
            key
            for key, value in provenance.items()
            if value.get("origin") == "OFICIAL" and value.get("accession") == accession
        ]
        if not cited:
            problems.append(
                f"accession {accession} verificado pero ningun hecho sale OFICIAL "
                f"(recall de la verificacion = 0)"
            )
    for key, value in sorted(provenance.items()):
        if value.get("origin") == "OFICIAL" and value.get("accession") not in official:
            problems.append(f"{key} es OFICIAL sin accession declarado en expected.index.official")
    for accession in unverified:
        cited = [
            key
            for key, value in provenance.items()
            if value.get("origin") == "OFICIAL" and value.get("accession") == accession
        ]
        if cited:
            problems.append(f"accession {accession} sin verificar declara OFICIAL: {cited}")
    return _result(
        "official_only_if_index_verified",
        not problems,
        problems[:10]
        or [
            f"{len(official)}/{len(verified)} accessions verificados llegan a OFICIAL; "
            f"0 hechos OFICIAL sin verificacion"
        ],
    )


def gate_absent_fields_reported_as_null(case: dict) -> dict:
    """Un campo que el fixture declara ausente no puede aparecer en la ingesta."""
    absent = (case.get("expected") or {}).get("absent_metrics")
    if absent is None:
        return _omitted(
            "absent_fields_reported_as_null",
            "absent_metrics",
            "sin lista de ausentes no hay fabricacion que detectar",
        )
    absent_metrics = list(absent)
    metrics = {fact["metric"] for fact in _observed_facts(case)}
    problems = [
        f"metrica declarada ausente reportada con valor: {metric}"
        for metric in absent_metrics
        if metric in metrics
    ]
    absent_values = (case.get("expected") or {}).get("absent_values") or []
    if absent_values:
        seen = {_as_decimal(fact.get("value")) for fact in _observed_facts(case)}
        for value in absent_values:
            if _as_decimal(value) in seen:
                problems.append(f"valor declarado ausente presente en la ingesta: {value}")
    return _result(
        "absent_fields_reported_as_null",
        not problems,
        problems[:10] or [f"{len(absent_metrics)} metricas ausentes siguen ausentes"],
    )


def gate_units_consistent(case: dict) -> dict:
    """La unidad del hecho es la que la metrica declara, y no se mezcla entre periodos."""
    observed = _observed_facts(case)
    problems: list[str] = []
    by_metric: dict[str, set[str]] = {}
    for fact in observed:
        by_metric.setdefault(fact["metric"], set()).add(fact["unit"])
    for metric, units in sorted(by_metric.items()):
        if len(units) > 1:
            problems.append(f"{metric}: unidades mezcladas {sorted(units)}")
    index = _facts_by_key(observed)
    for fact in _expected_facts(case):
        for row in index.get((fact["metric"], fact["period"])) or []:
            if row["unit"] != fact["unit"]:
                problems.append(
                    f"{fact['metric']}@{fact['period']}: unidad {row['unit']} != {fact['unit']}"
                )
    for metric, unit in sorted(((case.get("expected") or {}).get("units") or {}).items()):
        seen = by_metric.get(metric)
        if seen and seen != {unit}:
            problems.append(f"{metric}: unidades {sorted(seen)} != declaradas [{unit}]")
    return _result("units_consistent", not problems, problems[:10] or ["unidades coherentes"])


def gate_source_types_declared(case: dict) -> dict:
    """Cada hecho declara su fuente, y es la que el caso permite para su familia."""
    observed = _observed_facts(case)
    allowed = (case.get("expected") or {}).get("allowed_source_types") or FAMILY_SOURCE_TYPES.get(
        case.get("family") or "", ()
    )
    problems = [
        f"fuente no declarada o no permitida: {fact['metric']}@{fact['period']} "
        f"source_type={fact['source_type']!r}"
        for fact in observed
        if not fact.get("source_type") or fact["source_type"] not in allowed
    ]
    declared = (case.get("expected") or {}).get("source_types") or {}
    for fact in _expected_facts(case):
        wanted = declared.get(fact["metric"])
        if wanted is None:
            continue
        for row in _facts_by_key(observed).get((fact["metric"], fact["period"])) or []:
            if row["source_type"] != wanted:
                problems.append(
                    f"{fact['metric']}@{fact['period']}: fuente {row['source_type']} != {wanted}"
                )
    return _result(
        "source_types_declared",
        not problems,
        problems[:10] or [f"{len(observed)} hechos con fuente declarada"],
    )


def gate_duplicates_collapsed(case: dict) -> dict:
    """Un (metrica, periodo, fuente) aparece una vez, aunque el fixture lo repita."""
    seen: dict[tuple[str, str, str], int] = {}
    for fact in _observed_facts(case):
        key = (fact["metric"], fact["period"], fact["source_type"])
        seen[key] = seen.get(key, 0) + 1
    duplicates = sorted(key for key, count in seen.items() if count > 1)
    problems = [f"duplicado {key} x{seen[key]}" for key in duplicates]
    return _result("duplicates_collapsed", not problems, problems[:10] or [f"{len(seen)} series unicas"])


def gate_negative_controls_present(case: dict) -> dict:
    """El dataset tiene controles negativos, degradacion honesta y las tres familias."""
    summary = case.get("dataset_summary") or {}
    problems: list[str] = []
    for key, minimum in (
        ("cases", MIN_CASES),
        ("negative_controls", MIN_NEGATIVE_CONTROLS),
        ("degradation_cases", MIN_DEGRADATION_CASES),
    ):
        value = summary.get(key)
        if not isinstance(value, int) or value < minimum:
            problems.append(f"{key}={value!r} < {minimum}")
    families = summary.get("families") or {}
    for family in ("sec", "fmp", "esef"):
        count = families.get(family)
        if not isinstance(count, int) or count < MIN_FAMILY_CASES:
            problems.append(f"familia {family} con {count!r} casos (< {MIN_FAMILY_CASES})")
    if (families.get("sec") or 0) < MIN_SEC_CASES:
        problems.append(f"SEC/EDGAR con {families.get('sec')!r} casos (< {MIN_SEC_CASES})")
    problems.extend(
        f"control negativo sin expect_gate_failure: {cid}"
        for cid in (summary.get("negative_controls_not_declared") or [])
    )
    return _result(
        "negative_controls_present",
        not problems,
        problems[:10]
        or [
            f"{summary.get('cases')} casos, {summary.get('negative_controls')} controles "
            f"negativos, {summary.get('degradation_cases')} degradaciones honestas"
        ],
    )


GATES = {
    "fixture_schema_valid": gate_fixture_schema_valid,
    "extracted_values_match_fixture": gate_extracted_values_match_fixture,
    "period_attribution_correct": gate_period_attribution_correct,
    "no_lookahead": gate_no_lookahead,
    "official_only_if_index_verified": gate_official_only_if_index_verified,
    "absent_fields_reported_as_null": gate_absent_fields_reported_as_null,
    "units_consistent": gate_units_consistent,
    "source_types_declared": gate_source_types_declared,
    "duplicates_collapsed": gate_duplicates_collapsed,
    "negative_controls_present": gate_negative_controls_present,
}


def applies_to(case: dict, gate_name: str) -> bool:
    """Un caso se salta una puerta que no declara; el runner reporta cuantas corrieron.

    Las tres puertas no omitibles se ejecutan SIEMPRE: `applies_to` declara que un
    caso ejercita una puerta, no es una via para silenciar la que no se puede silenciar.
    """
    if gate_name in NON_SKIPPABLE_GATES:
        return True
    declared = case.get("applies_to")
    if declared is None:
        return True
    return gate_name in declared


def run_case(case: dict) -> list[dict]:
    return [gate(case) for gate in GATES.values()]