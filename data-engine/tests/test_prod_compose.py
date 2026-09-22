"""Regression tests for docker-compose.prod.yml deployment safety."""

from pathlib import Path

import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.prod.yml"


def _load_compose() -> dict:
    return yaml.safe_load(COMPOSE_PATH.read_text())


def _service_env(compose: dict, service: str) -> dict[str, str]:
    """Normalize a compose service environment (list or mapping form)."""
    env = compose["services"][service].get("environment", [])
    if isinstance(env, dict):
        return {str(k): str(v) for k, v in env.items()}
    result: dict[str, str] = {}
    for entry in env:
        key, _, value = str(entry).partition("=")
        result[key] = value
    return result


def test_backend_does_not_duplicate_the_standalone_scheduler():
    """The backend embeds a scheduler when WORKERS_ENABLED=true (the default).

    docker-compose.prod.yml also runs a dedicated scheduler service, so the
    backend must set WORKERS_ENABLED=false or every periodic job fires twice.
    """
    compose = _load_compose()
    assert "scheduler" in compose["services"], "expected a standalone scheduler service"
    backend_env = _service_env(compose, "backend")
    assert backend_env.get("WORKERS_ENABLED") == "false", (
        "backend service must disable its embedded scheduler "
        "(WORKERS_ENABLED=false) because cavaai-scheduler runs it"
    )


def test_prod_backend_forces_signed_research_identity():
    compose = _load_compose()
    backend_env = _service_env(compose, "backend")
    assert backend_env.get("APP_ENV") == "production"
    assert backend_env.get("RESEARCH_AUTH_REQUIRED") == "true"
