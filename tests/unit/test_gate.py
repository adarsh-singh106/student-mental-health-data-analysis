import pytest

from mental_health.models.gate import gate, GateFailedError


def test_gate_passes_for_good_model():
    """Achha model — gap chhota, thresholds paar → True."""
    stats = {
        "train": {"r2": 0.9821, "mae": 0.12, "rmse": 0.17},
        "test":  {"r2": 0.8902, "mae": 0.3258, "rmse": 0.4391},
    }
    assert gate(stats) is True


def test_gate_raises_on_overfit():
    """Train achha, test kharab — gap 0.15 se bada → raise."""
    stats = {
        "train": {"r2": 0.99, "mae": 0.05, "rmse": 0.08},
        "test":  {"r2": 0.70, "mae": 0.30, "rmse": 0.45},
    }
    with pytest.raises(GateFailedError):
        gate(stats)


def test_gate_raises_on_underperforming():
    """Gap toh chhota, par test r2 0.85 se neeche → raise."""
    stats = {
        "train": {"r2": 0.80, "mae": 0.40, "rmse": 0.55},
        "test":  {"r2": 0.75, "mae": 0.40, "rmse": 0.55},
    }
    with pytest.raises(GateFailedError):
        gate(stats)