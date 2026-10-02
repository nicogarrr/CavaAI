"""C4: mide la PRECISION de la ingesta contra el corpus sintetico.

Ejecuta la ingesta real (`evals/ingest/harness.py`) sobre cada caso del dataset
congelado, pasa el resultado por las hard gates deterministas y emite cuatro
numeros con umbral:

1. field accuracy                  (>= 0.98)
2. period attribution accuracy     (>= 0.95)
3. source attribution accuracy     (>= 0.99)
4. abstention / no-fabrication     (= 1.00, no negociable)

Ademas imprime la cobertura por puerta y por familia de fuente y FALLA si una
puerta o una familia corrio 0 veces: una puerta que nadie ejercita no es una
puerta, es decoracion.

Uso:
    python data-engine/scripts/run_ingest_evals.py            # texto
    python data-engine/scripts/run_ingest_evals.py --json     # una linea JSON

Determinista y offline: sin red (guardian de sockets) y sin LLM. Exit 1 si
cualquier umbral no se alcanza, si un control negativo no muerde o si una puerta
o familia nunca se ejecuto.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.ingest import harness  # noqa: E402
from evals.ingest import ingest_gates as gates  # noqa: E402

DATASET = ROOT / "evals" / "ingest" / "ingest_v1.json"
FAMILIES = ("sec", "fmp", "esef")
METRICS = {
    "field_accuracy": 0.98,
    "period_attribution_accuracy": 0.95,
    "source_attribution_accuracy": 0.99,
    "abstention_rate": 1.0,
}
# Puertas cuyo control negativo lo aporta el dataset, no una cuenta sintetica.
COMPOSITION_GATES = ("fixture_schema_valid", "duplicates_collapsed",
                     "negative_controls_present")


# --------------------------------------------------------------------------
# Aritmetica Decimal: el runner no introduce error de punto flotante
# --------------------------------------------------------------------------


def _decimal(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001 - un valor no numerico simplemente no cuenta
        return None


def _tolerance(case: dict) -> tuple[Decimal, Decimal]:
    declared = (case.get("expected") or {}).get("tolerance") or {}
    return (
        _decimal(declared.get("relative")) or Decimal("0"),
        _decimal(declared.get("absolute")) or Decimal("0"),
    )


def _matches(actual, expected, tolerance: tuple[Decimal, Decimal]) -> bool:
    left = _decimal(actual)
    right = _decimal(expected)
    if left is None or right is None:
        return actual == expected
    relative, absolute = tolerance
    return abs(left - right) <= max(absolute, relative * abs(right))


# Una sola implementacion de "que es una fecha de periodo", la de las puertas:
# con dos versiones, una etiqueta como `2025-99-99:FY` pasaba la dura y la
# suave no coincidian (FIX5-10).
_period_date = gates._period_date


class Counters:
    """Aciertos y totales de las cuatro metricas, globales y por familia."""

    def __init__(self) -> None:
        self.totals: dict[str, int] = {}
        self.hits: dict[str, int] = {}
        self.by_family: dict[str, dict[str, list[int]]] = {}

    def hit(self, metric: str, family: str) -> None:
        self.totals[metric] = self.totals.get(metric, 0) + 1
        self.hits[metric] = self.hits.get(metric, 0) + 1
        bucket = self._bucket(metric, family)
        bucket[0] += 1
        bucket[1] += 1

    def miss(self, metric: str, family: str) -> None:
        self.totals[metric] = self.totals.get(metric, 0) + 1
        self._bucket(metric, family)[1] += 1

    def _bucket(self, metric: str, family: str) -> list[int]:
        return self.by_family.setdefault(metric, {}).setdefault(family, [0, 0])

    def rate(self, metric: str) -> float:
        total = self.totals.get(metric, 0)
        return 0.0 if not total else self.hits.get(metric, 0) / total


# --------------------------------------------------------------------------
# Medicion
# --------------------------------------------------------------------------


def score_case(case: dict, observation: dict, counters: Counters) -> list[str]:
    """Acumula las cuatro metricas del caso. Devuelve los fallos de medicion."""
    expected = case.get("expected") or {}
    family = case.get("family") or "?"
    facts = [row for row in observation.get("facts") or [] if "metric" in row]
    provenance = observation.get("provenance") or {}
    index_block = expected.get("index") or {}
    official_accessions = list(index_block.get("official") or [])
    tolerance = _tolerance(case)
    problems: list[str] = []

    by_key: dict[tuple[str, str], list[dict]] = {}
    for fact in facts:
        if "metric" not in fact:
            continue
        by_key.setdefault((fact["metric"], fact["period"]), []).append(fact)

    for declared in expected.get("facts") or []:
        key = (declared["metric"], declared["period"])
        rows = by_key.get(key) or []
        row = next((r for r in rows if _matches(r.get("value"), declared["value"], tolerance)), None)
        if row is None:
            counters.miss("field_accuracy", family)
            counters.miss("period_attribution_accuracy", family)
            counters.miss("source_attribution_accuracy", family)
            problems.append(
                f"field accuracy: {declared['metric']}@{declared['period']} ausente o distinto "
                f"de {declared['value']}"
            )
            continue
        counters.hit("field_accuracy", family)
        wanted_period = (
            declared.get("fiscal_year", row["fiscal_year"]),
            declared.get("fiscal_quarter", row["fiscal_quarter"]),
        )
        if (row["fiscal_year"], row["fiscal_quarter"]) == wanted_period:
            counters.hit("period_attribution_accuracy", family)
        else:
            counters.miss("period_attribution_accuracy", family)
            problems.append(
                f"period attribution: {declared['metric']}@{declared['period']} "
                f"fy={row['fiscal_year']}/fq={row['fiscal_quarter']} != {wanted_period}"
            )
        wanted_origin = declared.get("origin")
        if wanted_origin is None:
            counters.hit("source_attribution_accuracy", family)
        else:
            resolved = provenance.get(f"{declared['metric']}@{declared['period']}") or {}
            verifiable = (
                "OFICIAL"
                if resolved.get("origin") == "OFICIAL"
                and resolved.get("accession") in official_accessions
                else "INFERIDO"
            )
            if verifiable == wanted_origin:
                counters.hit("source_attribution_accuracy", family)
            else:
                counters.miss("source_attribution_accuracy", family)
                problems.append(
                    f"source attribution: {declared['metric']}@{declared['period']} "
                    f"declarado {wanted_origin}, verificable {verifiable}"
                )

    normalized = {
        (row.get("concept"), row.get("unit")): row.get("entries")
        for row in observation.get("facts") or []
        if "concept" in row
    }
    for declared in expected.get("normalized_facts") or []:
        key = (declared.get("concept"), declared.get("unit"))
        if normalized.get(key) == declared.get("entries"):
            counters.hit("field_accuracy", family)
        else:
            counters.miss("field_accuracy", family)
            problems.append(
                f"field accuracy: concepto {key} con {normalized.get(key)} entradas "
                f"!= declaradas {declared.get('entries')}"
            )

    requested = observation.get("requests") or []
    for declared in expected.get("requests") or []:
        found = next((r for r in requested if r.get("path") == declared.get("path")), None)
        ok = found is not None and all(
            str(found.get("params", {}).get(key)) == str(value)
            for key, value in (declared.get("params") or {}).items()
        )
        if ok:
            counters.hit("field_accuracy", family)
        else:
            counters.miss("field_accuracy", family)
            problems.append(f"field accuracy: peticion {declared.get('path')} no coincide")

    for accession in official_accessions:
        cited = [
            key
            for key, value in provenance.items()
            if value.get("origin") == "OFICIAL" and value.get("accession") == accession
        ]
        if cited:
            counters.hit("source_attribution_accuracy", family)
        else:
            counters.miss("source_attribution_accuracy", family)
            problems.append(
                f"source attribution: accession verificado {accession} no llega a OFICIAL"
            )
    for accession in index_block.get("unverified") or []:
        cited = [
            key
            for key, value in provenance.items()
            if value.get("origin") == "OFICIAL" and value.get("accession") == accession
        ]
        if cited:
            counters.miss("source_attribution_accuracy", family)
            problems.append(
                f"source attribution: accession sin verificar {accession} sale OFICIAL"
            )
        else:
            counters.hit("source_attribution_accuracy", family)

    present_metrics = {fact["metric"] for fact in facts}
    for metric in expected.get("absent_metrics") or []:
        if metric in present_metrics:
            counters.miss("abstention_rate", family)
            problems.append(f"abstention: metrica declarada ausente reportada ({metric})")
        else:
            counters.hit("abstention_rate", family)
    observed_values = {_decimal(fact.get("value")) for fact in facts}
    for value in expected.get("absent_values") or []:
        if _decimal(value) in observed_values:
            counters.miss("abstention_rate", family)
            problems.append(f"abstention: valor declarado ausente presente ({value})")
        else:
            counters.hit("abstention_rate", family)

    as_of = expected.get("as_of")
    if isinstance(as_of, str) and len(as_of) >= 10:
        leaked = []
        unreadable = []
        for fact in facts:
            head, problem = _period_date(fact["period"])
            if problem:
                unreadable.append(fact)
            elif head and head > as_of[:10]:
                leaked.append(fact)
        if leaked:
            counters.miss("abstention_rate", family)
            problems.append(
                f"abstention: {len(leaked)} hecho(s) de un periodo posterior a {as_of}"
            )
        elif unreadable:
            # Una etiqueta sin fecha legible no se puede acotar en el tiempo:
            # lo mismo de antes, el hecho se salia del filtro sin que nadie lo
            # viera (FIX5-10).
            counters.miss("abstention_rate", family)
            problems.append(
                f"abstention: {len(unreadable)} etiqueta(s) de periodo no parseable(s)"
            )
        else:
            counters.hit("abstention_rate", family)
        if any(_decimal(value) in observed_values for value in expected.get("forbidden_values") or []):
            counters.miss("abstention_rate", family)
            problems.append("abstention: valor declarado de look-ahead presente en la ingesta")
        else:
            counters.hit("abstention_rate", family)
    else:
        counters.miss("abstention_rate", family)
        problems.append("abstention: expected.as_of ausente, el caso no se puede puntuar")
    return problems


# --------------------------------------------------------------------------
# Corrida
# --------------------------------------------------------------------------


def dataset_summary(dataset: dict) -> dict:
    cases = dataset["cases"]
    negatives = [case for case in cases if case.get("expect_gate_failure")]
    covered = {case["expect_gate_failure"] for case in negatives}
    return {
        "cases": len(cases),
        "negative_controls": len(negatives),
        "degradation_cases": len([case for case in cases if case.get("category") == "degradation"]),
        "families": {
            family: len([case for case in cases if case.get("family") == family])
            for family in FAMILIES
        },
        "negative_controls_not_declared": [
            name for name in gates.GATES
            if name not in covered and name not in COMPOSITION_GATES
        ],
    }


def run(dataset: dict) -> dict:
    summary = dataset_summary(dataset)
    counters = Counters()
    executed = dict.fromkeys(gates.GATES, 0)
    family_cases: dict[str, int] = dict.fromkeys(FAMILIES, 0)
    failures: list[str] = []
    per_case: list[dict] = []
    checks = 0

    composition_case = {
        "id": "__dataset__",
        "family": "sec",
        "scenario": "sec_companyfacts",
        "dataset_summary": summary,
        "expected": {"facts": []},
        "observed": {"facts": []},
        "applies_to": ["negative_controls_present"],
    }
    result = gates.gate_negative_controls_present(composition_case)
    checks += 1
    executed["negative_controls_present"] += 1
    if not result["passed"]:
        failures.append(f"__dataset__: negative_controls_present fallo: {'; '.join(result['details'])}")

    for case in dataset["cases"]:
        family = case.get("family") or "?"
        family_cases[family] = family_cases.get(family, 0) + 1
        expected_failure = case.get("expect_gate_failure")
        try:
            observation = harness.run_case(case)
        except Exception as exc:  # noqa: BLE001 - un escenario roto es un fallo del eval
            failures.append(f"{case['id']}: escenario {case.get('scenario')} fallo: {exc!r}")
            per_case.append({"id": case["id"], "family": family, "status": "harness_error",
                             "error": repr(exc)})
            continue
        merged = {**case, "observed": observation}
        problems = [] if expected_failure else score_case(case, observation, counters)
        gate_results: list[str] = []
        for gate_name, gate in gates.GATES.items():
            if gate_name == "negative_controls_present":
                continue
            if not gates.applies_to(case, gate_name):
                continue
            outcome = gate(merged)
            checks += 1
            executed[gate_name] += 1
            gate_results.append(f"{gate_name}={'ok' if outcome['passed'] else 'FAIL'}")
            if expected_failure == gate_name:
                if outcome["passed"]:
                    failures.append(
                        f"{case['id']}: {gate_name} debia FALLAR (control negativo) y paso"
                    )
            elif not outcome["passed"]:
                failures.append(
                    f"{case['id']}: {gate_name} fallo: {'; '.join(outcome['details'])}"
                )
        failures.extend(f"{case['id']}: {problem}" for problem in problems)
        per_case.append(
            {
                "id": case["id"],
                "family": family,
                "category": case.get("category"),
                "status": observation.get("status"),
                "control": expected_failure,
                "gates": gate_results,
                "problems": problems,
            }
        )

    never_ran = sorted(name for name, count in executed.items() if count == 0)
    if never_ran:
        failures.append("puertas que nunca se ejecutaron: " + ", ".join(never_ran))
    empty_families = sorted(name for name, count in family_cases.items() if not count)
    if empty_families:
        failures.append("familias de fuente sin ningun caso: " + ", ".join(empty_families))

    metrics: dict[str, dict] = {}
    for metric, threshold in METRICS.items():
        rate = counters.rate(metric)
        passed = rate >= threshold
        metrics[metric] = {
            "value": round(rate, 6),
            "threshold": threshold,
            "passed": passed,
            "hits": counters.hits.get(metric, 0),
            "total": counters.totals.get(metric, 0),
        }
        if not passed:
            failures.append(
                f"{metric}={rate:.4f} por debajo del umbral {threshold} "
                f"({metrics[metric]['hits']}/{metrics[metric]['total']})"
            )
    sub_metrics = {
        metric: {
            family: {
                "hits": bucket[0],
                "total": bucket[1],
                "value": round(bucket[0] / bucket[1], 6) if bucket[1] else None,
            }
            for family, bucket in sorted(families.items())
        }
        for metric, families in sorted(counters.by_family.items())
    }
    return {
        "dataset": dataset.get("dataset"),
        "cases": len(dataset["cases"]),
        "checks": checks,
        "metrics": metrics,
        "sub_metrics": sub_metrics,
        "gate_coverage": dict(sorted(executed.items())),
        "family_cases": dict(sorted(family_cases.items())),
        "dataset_summary": summary,
        "failures": failures,
        "per_case": per_case,
        "passed": not failures,
    }


def render_text(report: dict) -> str:
    lines = [
        f"Dataset {report['dataset']}: {report['cases']} casos -> {report['checks']} checks",
        "",
        "METRICAS (umbrales):",
    ]
    for metric, data in report["metrics"].items():
        mark = "OK   " if data["passed"] else "FALLA"
        lines.append(
            f"  {mark} {metric:32} {data['value']:.4f}  (>= {data['threshold']})"
            f"  [{data['hits']}/{data['total']}]"
        )
    lines.append("")
    lines.append("SUB-METRICAS por familia de fuente:")
    for metric, families in report["sub_metrics"].items():
        for family, data in families.items():
            value = "n/d" if data["value"] is None else f"{data['value']:.4f}"
            lines.append(f"  {metric:32} {family:5} {value:>7}  [{data['hits']}/{data['total']}]")
    lines.append("")
    lines.append("Cobertura por puerta:")
    for name, count in report["gate_coverage"].items():
        marker = "  <-- NUNCA SE EJECUTO" if count == 0 else ""
        required = " (no omitible)" if name in gates.NON_SKIPPABLE_GATES else ""
        lines.append(f"  {name:34} {count}{required}{marker}")
    lines.append("")
    lines.append("Cobertura por familia de fuente:")
    for name, count in report["family_cases"].items():
        marker = "  <-- SIN CASOS" if count == 0 else ""
        lines.append(f"  {name:34} {count}{marker}")
    summary = report["dataset_summary"]
    lines.append("")
    lines.append(
        f"Controles negativos: {summary['negative_controls']} | degradacion honesta: "
        f"{summary['degradation_cases']}"
    )
    if report["failures"]:
        lines.append("")
        lines.append(f"{len(report['failures'])} FALLOS:")
        lines.extend(f"  - {failure}" for failure in report["failures"][:80])
        extra = len(report["failures"]) - 80
        if extra > 0:
            lines.append(f"  ... y {extra} mas")
        return "\n".join(lines)
    lines.append("")
    lines.append("Todos los gates en verde.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Precision de la ingesta (C4).")
    parser.add_argument("--json", action="store_true", help="una sola linea JSON para CI")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    args = parser.parse_args(argv)
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = run(dataset)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(render_text(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
