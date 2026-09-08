import pytest

from mental_health.models.train import build_pipeline


def test_build_pipeline_preserves_the_default_release_configuration():
    pipeline = build_pipeline()

    assert pipeline.named_steps["model"].min_samples_leaf == 1
    assert pipeline.named_steps["model"].n_jobs == 1


def test_build_pipeline_allows_a_shadow_candidate_configuration():
    pipeline = build_pipeline(min_samples_leaf=5)

    assert pipeline.named_steps["model"].min_samples_leaf == 5


def test_build_pipeline_rejects_an_invalid_leaf_size():
    with pytest.raises(ValueError, match="at least 1"):
        build_pipeline(min_samples_leaf=0)
