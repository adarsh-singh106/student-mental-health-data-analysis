import pytest

from mental_health.models.gate import gate, GateFailedError, MAX_CV_MAE


def test_gate_passes_when_cv_mae_upper_below_bar():
    """mean + std clearly under the bar → True."""
    cv_stats = {"mae_mean": 0.34, "mae_std": 0.01, "r2_mean": 0.86, "r2_std": 0.01}
    assert gate(cv_stats) is True


def test_gate_raises_when_mean_alone_breaches():
    """Even before adding std, the mean is already over the bar → raise."""
    cv_stats = {"mae_mean": 0.42, "mae_std": 0.01, "r2_mean": 0.80, "r2_std": 0.02}
    with pytest.raises(GateFailedError):
        gate(cv_stats)


def test_gate_raises_when_std_pushes_over_bar():
    """Mean is under the bar, but the spread pushes the worst case over → raise.
    This is the whole point of adding std: a wobbly model must fail."""
    cv_stats = {"mae_mean": 0.39, "mae_std": 0.03, "r2_mean": 0.84, "r2_std": 0.05}
    assert cv_stats["mae_mean"] < MAX_CV_MAE          # mean alone would pass
    assert cv_stats["mae_mean"] + cv_stats["mae_std"] > MAX_CV_MAE  # spread fails it
    with pytest.raises(GateFailedError):
        gate(cv_stats)
