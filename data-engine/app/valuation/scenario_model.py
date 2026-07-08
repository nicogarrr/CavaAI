from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    probability: float
    value_per_share: float


def probability_weighted_value(scenarios: list[Scenario]) -> dict:
    if not scenarios:
        raise ValueError("at least one scenario is required")

    probability_sum = sum(s.probability for s in scenarios)
    if probability_sum <= 0:
        raise ValueError("scenario probabilities must be positive")

    normalized = [
        Scenario(s.name, s.probability / probability_sum, s.value_per_share) for s in scenarios
    ]
    expected_value = sum(s.probability * s.value_per_share for s in normalized)
    return {
        "expected_value": expected_value,
        "scenarios": [s.__dict__ for s in normalized],
        "trace": {"method": "probability_weighted_scenario", "probability_sum": probability_sum},
    }

