"""Puertas de seguridad de las 4 imagenes Docker del repo (tarea E3).

El veredicto rojo/verde vive aqui y no en el YAML del workflow. Dos motivos:

1. Es testeable sin docker ni runner: `tests/test_supply_chain_contracts.py`
   mete informes sinteticos y comprueba que la puerta decide lo que tiene que
   decidir, incluido el caso "el escaner no llego a ejecutarse".
2. El YAML no lleva `exit-code` ni `--ignore` que decidan por su cuenta: el
   unico exit code que manda es el de este modulo, y las excepciones estan en
   scripts/security/trivy-policy.yaml (versionado, con ticket y caducidad).

Politica implementada:

- CVE CRITICAL con fix disponible ................ rojo
- secret en la imagen, cualquier severidad ..... rojo
- misconfiguration HIGH o CRITICAL ............... rojo
- CVE HIGH/MEDIUM/LOW ........................... se reportan con su numero
- build roto o escaner que no se ejecuta ......... rojo (fail-closed)

Se ejecuta en el runner con `python -m scripts.security.gate_image_scan`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

CRITICAL = "CRITICAL"
HIGH = "HIGH"
BLOCKING_MISCONFIG_SEVERITIES = frozenset({HIGH, CRITICAL})
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
REQUIRED_EXCEPTION_FIELDS = ("id", "scope", "reason", "ticket", "expires")
VALID_SCOPES = frozenset({"vulnerability", "secret", "misconfig"})

# (flag del informe, kind, motor). Los cuatro informes son obligatorios: que
# falte cualquiera de ellos es un escaner que no se ejecutó, no un "0 hallazgos".
REPORT_SLOTS = (
    ("vuln", "vulnerability", "trivy"),
    ("secret", "secret", "trivy"),
    ("misconfig", "misconfig", "trivy"),
    ("second", "vulnerability", "anchore-scan"),
)
SLOT_FLAGS = {
    "vuln": ("--vuln-report", "--vuln-status"),
    "secret": ("--secret-report", "--secret-status"),
    "misconfig": ("--misconfig-report", "--misconfig-status"),
    "second": ("--second-report", "--second-status"),
}


class GateError(Exception):
    """El gate no puede decidir. Nunca se interpreta como aprobado."""


@dataclass(frozen=True)
class Finding:
    severity: str
    identifier: str
    package: str = ""
    fixed: bool = False
    target: str = ""
    title: str = ""


@dataclass
class Report:
    kind: str
    engine: str
    source: str
    findings: list[Finding] = field(default_factory=list)


@dataclass(frozen=True)
class ExceptionEntry:
    identifier: str
    scope: str
    targets: tuple[str, ...]
    paths: tuple[str, ...]
    reason: str
    ticket: str
    expires: date

    def covers(self, kind: str, finding: Finding, image: str) -> bool:
        if self.scope != kind:
            return False
        if self.identifier.strip().upper() != finding.identifier.strip().upper():
            return False
        if self.targets and image not in self.targets:
            return False
        # `paths` acota la excepcion a ficheros concretos (p. ej. un Dockerfile).
        return not self.paths or finding.target in self.paths


@dataclass
class Gate:
    image: str
    image_ref: str = ""
    blocks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.blocks and not self.errors

    def as_dict(self) -> dict:
        return {
            "image": self.image,
            "image_ref": self.image_ref,
            "passed": self.passed,
            "blocks": self.blocks,
            "errors": self.errors,
            "notes": self.notes,
            "counts": self.counts,
        }


def _severity(value: object) -> str:
    text = str(value or "UNKNOWN").strip().upper()
    return text if text in SEVERITIES else "UNKNOWN"


def _first_line(value: object, limit: int = 120) -> str:
    lines = str(value or "").strip().splitlines()
    return (lines[0] if lines else "")[:limit]


def _trivy_vulnerabilities(payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for result in payload.get("Results") or []:
        target = str(result.get("Target") or "")
        for vuln in result.get("Vulnerabilities") or []:
            findings.append(
                Finding(
                    severity=_severity(vuln.get("Severity")),
                    identifier=str(vuln.get("VulnerabilityID") or ""),
                    package=f"{vuln.get('PkgName') or ''} {vuln.get('InstalledVersion') or ''}".strip(),
                    fixed=bool(str(vuln.get("FixedVersion") or "").strip()),
                    target=target,
                    title=_first_line(vuln.get("Title")),
                )
            )
    return findings


def _grype_vulnerabilities(payload: dict) -> list[Finding]:
    """anchore/scan-action devuelve JSON de grype, no de trivy: otro motor, otro formato."""
    findings: list[Finding] = []
    for match in payload.get("matches") or []:
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        fix = vuln.get("fix") or {}
        name = str(artifact.get("name") or "")
        findings.append(
            Finding(
                severity=_severity(vuln.get("severity")),
                identifier=str(vuln.get("id") or ""),
                package=f"{name} {artifact.get('version') or ''}".strip(),
                fixed=bool(fix.get("versions")),
                target=str(artifact.get("location") or ""),
                title=_first_line(vuln.get("description")),
            )
        )
    return findings


def _trivy_secrets(payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for result in payload.get("Results") or []:
        target = str(result.get("Target") or "")
        for secret in result.get("Secrets") or []:
            line = secret.get("StartLine", "?")
            findings.append(
                Finding(
                    severity=_severity(secret.get("Severity")),
                    identifier=str(secret.get("RuleID") or secret.get("Category") or "SECRET"),
                    package=str(secret.get("Category") or ""),
                    target=f"{target}:{line}",
                    title=_first_line(secret.get("Title")),
                )
            )
    return findings


def _trivy_misconfigs(payload: dict) -> list[Finding]:
    findings: list[Finding] = []
    for result in payload.get("Results") or []:
        target = str(result.get("Target") or "")
        for item in result.get("Misconfigurations") or []:
            findings.append(
                Finding(
                    severity=_severity(item.get("Severity")),
                    identifier=str(item.get("ID") or item.get("AVDID") or ""),
                    package=target,
                    target=target,
                    title=_first_line(item.get("Title")),
                )
            )
    return findings


def load_report(path: Path, kind: str, engine: str) -> Report:
    if not path.is_file():
        raise GateError(f"informe ausente ({engine}/{kind}): {path} -> el escaner no se ejecuto")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GateError(f"informe ilegible ({engine}/{kind}): {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateError(f"informe con forma inesperada ({engine}/{kind}): {path}")
    if kind == "secret":
        findings = _trivy_secrets(payload)
    elif kind == "misconfig":
        findings = _trivy_misconfigs(payload)
    elif engine == "trivy":
        findings = _trivy_vulnerabilities(payload)
    else:
        findings = _grype_vulnerabilities(payload)
    return Report(kind=kind, engine=engine, source=str(path), findings=findings)


def load_policy(path: Path, today: date) -> tuple[list[ExceptionEntry], list[str]]:
    """Devuelve (excepciones validas, errores de contrato). Los errores son puerta roja."""
    if not path.is_file():
        raise GateError(f"politica de excepciones ausente: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise GateError(f"politica de excepciones ilegible: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise GateError(f"politica de excepciones con forma inesperada: {path}")

    raw = payload.get("exceptions") or []
    if not isinstance(raw, list):
        raise GateError(f"{path}: 'exceptions' debe ser una lista")

    entries: list[ExceptionEntry] = []
    errors: list[str] = []
    for index, item in enumerate(raw):
        where = f"{path}:exceptions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: la excepcion no es un mapa")
            continue
        missing = [name for name in REQUIRED_EXCEPTION_FIELDS if not str(item.get(name) or "").strip()]
        if missing:
            errors.append(
                f"{where}: faltan campos obligatorios {missing} "
                "(una excepcion sin expires es una vulnerabilidad silenciada para siempre)"
            )
            continue
        scope = str(item["scope"]).strip().lower()
        if scope not in VALID_SCOPES:
            errors.append(f"{where}: scope {scope!r} no permitido ({sorted(VALID_SCOPES)})")
            continue
        try:
            expires = date.fromisoformat(str(item["expires"]).strip())
        except ValueError:
            errors.append(f"{where}: expires {item['expires']!r} no es una fecha ISO (YYYY-MM-DD)")
            continue
        if expires < today:
            errors.append(
                f"{where}: excepcion {item['id']} caducada el {expires.isoformat()}; "
                "borrarla o renovarla con su ticket (no se ignora en silencio)"
            )
            continue
        targets = item.get("targets") or []
        if isinstance(targets, str):
            targets = [targets]
        entries.append(
            ExceptionEntry(
                identifier=str(item["id"]).strip(),
                scope=scope,
                targets=tuple(str(target).strip() for target in targets),
                paths=tuple(str(path).strip() for path in _as_list(item.get("paths"))),
                reason=str(item["reason"]).strip(),
                ticket=str(item["ticket"]).strip(),
                expires=expires,
            )
        )
    return entries, errors


def _as_list(value: object) -> list:
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)  # type: ignore[call-overload]


def _verdict(gate: Gate, report: Report, exceptions: list[ExceptionEntry]) -> None:
    counts: dict[str, int] = {}
    excepted = 0
    for finding in report.findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        if any(entry.covers(report.kind, finding, gate.image) for entry in exceptions):
            excepted += 1
            continue
        if report.kind == "secret":
            # Cualquier secret, en cualquier severidad: un token en una capa es
            # un token quemado aunque trivy lo puntue LOW.
            gate.blocks.append(
                f"[{gate.image}] SECRET {finding.identifier} en {finding.target}: {finding.title}"
            )
        elif report.kind == "misconfig":
            if finding.severity in BLOCKING_MISCONFIG_SEVERITIES:
                gate.blocks.append(
                    f"[{gate.image}] MISCONFIG {finding.severity} {finding.identifier} "
                    f"en {finding.target}: {finding.title}"
                )
        elif finding.severity == CRITICAL and finding.fixed:
            gate.blocks.append(
                f"[{gate.image}] CVE CRITICAL con fix {finding.identifier} "
                f"({finding.package}) en {finding.target}"
            )
    for severity in SEVERITIES:
        if counts.get(severity):
            gate.counts[f"{report.engine}:{report.kind}:{severity}"] = counts[severity]
    if excepted:
        gate.notes.append(
            f"[{gate.image}] {excepted} hallazgo(s) de {report.engine}/{report.kind} "
            "cubiertos por scripts/security/trivy-policy.yaml"
        )
    reported = ", ".join(
        f"{severity}={counts[severity]}" for severity in SEVERITIES if counts.get(severity)
    )
    gate.notes.append(
        f"[{gate.image}] {report.engine}/{report.kind}: {reported or 'sin hallazgos'} "
        f"(los HIGH/MEDIUM se reportan, no bloquean)"
    )


def evaluate(
    *,
    image: str,
    image_ref: str = "",
    build_result: str = "success",
    reports: list[Report],
    exceptions: list[ExceptionEntry],
    policy_errors: list[str],
) -> Gate:
    gate = Gate(image=image, image_ref=image_ref)
    gate.errors.extend(policy_errors)
    if build_result != "success":
        gate.errors.append(
            f"[{image}] el build termino en {build_result!r}: sin imagen no hay escaneo, "
            "y un escaneo que no corre no es un escaneo limpio (fail-closed)"
        )
    for report in reports:
        _verdict(gate, report, exceptions)
    return gate


def render(gate: Gate) -> str:
    lines = [f"gate {gate.image} ({gate.image_ref or 'sin ref'})"]
    lines += [f"  ERROR  {error}" for error in gate.errors]
    lines += [f"  BLOQUEO {block}" for block in gate.blocks]
    lines += [f"  info   {note}" for note in gate.notes]
    lines.append("  VEREDICTO: VERDE" if gate.passed else "  VEREDICTO: ROJO")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Puertas de seguridad de imagenes Docker (E3).")
    parser.add_argument("--image", required=True, help="nombre de la imagen en la matriz")
    parser.add_argument("--image-ref", default="", help="tag/digest de la imagen escaneada")
    parser.add_argument(
        "--build-result",
        required=True,
        choices=["success", "failure", "cancelled", "skipped"],
        help="resultado del job build (todo distinto de success es puerta roja)",
    )
    parser.add_argument("--policy", required=True, type=Path, help="scripts/security/trivy-policy.yaml")
    parser.add_argument("--summary", type=Path, default=None, help="JSON de resumen para artefacto")
    for report_flag, status_flag in SLOT_FLAGS.values():
        parser.add_argument(report_flag, type=Path, default=None, help="informe JSON del escaner")
        parser.add_argument(status_flag, default="success", help="outcome del paso que lo produjo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        exceptions, policy_errors = load_policy(args.policy, date.today())
    except GateError as exc:
        print(f"::error::{exc}")
        print(f"gate {args.image}\n  VEREDICTO: ROJO")
        return 1

    reports: list[Report] = []
    errors: list[str] = list(policy_errors)
    for slot, kind, engine in REPORT_SLOTS:
        report_flag, status_flag = SLOT_FLAGS[slot]
        path = getattr(args, report_flag.lstrip("-").replace("-", "_"))
        status = getattr(args, status_flag.lstrip("-").replace("-", "_"))
        if status != "success":
            errors.append(f"[{args.image}] paso {slot} termino en {status!r}: escaneo incompleto")
        if path is None:
            errors.append(f"[{args.image}] no se paso informe para {slot} ({engine}/{kind})")
            continue
        try:
            reports.append(load_report(path, kind, engine))
        except GateError as exc:
            errors.append(f"[{args.image}] {exc}")

    gate = evaluate(
        image=args.image,
        image_ref=args.image_ref,
        build_result=args.build_result,
        reports=reports,
        exceptions=exceptions,
        policy_errors=errors,
    )
    print(render(gate))
    for message in [*gate.errors, *gate.blocks]:
        print(f"::error::{message}")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(gate.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if gate.passed else 1


if __name__ == "__main__":  # pragma: no cover - entrypoint de CLI
    sys.exit(main())