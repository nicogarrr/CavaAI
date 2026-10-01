"""F367: el max drawdown parte del patrimonio inicial."""
import pytest

from app.services.tearsheet_service import compute_metrics


def test_first_period_loss_is_a_drawdown():
    metrics = compute_metrics([-0.5, 0.1])
    assert metrics["max_drawdown"] == pytest.approx(-0.5)


def test_only_gains_have_zero_drawdown():
    assert compute_metrics([0.1, 0.1])["max_drawdown"] == pytest.approx(0.0)


def test_later_drawdown_unchanged():
    assert compute_metrics([0.2, -0.25, 0.05])["max_drawdown"] == pytest.approx(-0.25)
