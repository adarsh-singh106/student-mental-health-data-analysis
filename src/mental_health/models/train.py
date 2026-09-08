"""Fit and evaluate the project's sklearn pipeline from a supplied CSV."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import cross_validate, train_test_split
from sklearn.pipeline import Pipeline

from mental_health.data.preparation import prepare_data
from mental_health.data.schema import FEATURE_SCHEMA_VERSION, TARGET_COLUMN
from mental_health.features.preprocessing import build_preprocessor


logger = logging.getLogger(__name__)


def _compute_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def build_pipeline(*, min_samples_leaf: int = 1) -> Pipeline:
    """Construct the fitted-model shape without changing the default release."""
    if min_samples_leaf < 1:
        raise ValueError("min_samples_leaf must be at least 1")
    return Pipeline(
        [
            ("prep", build_preprocessor()),
            (
                "model",
                RandomForestRegressor(
                    random_state=42,
                    n_jobs=1,
                    min_samples_leaf=min_samples_leaf,
                ),
            ),
        ]
    )


def train(path: Path, *, min_samples_leaf: int = 1) -> tuple[Pipeline, dict, dict]:
    """Prepare data, evaluate the candidate, and return the fitted release model."""
    path = Path(path)
    logger.info("training started | data=%s", path)
    prepared_df = prepare_data(path)

    dataset = {
        "file": path.name,
        "rows": len(prepared_df),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "schema_version": FEATURE_SCHEMA_VERSION,
    }

    X = prepared_df.drop(columns=[TARGET_COLUMN])
    y = prepared_df[TARGET_COLUMN]

    # Hold out 20% before anything used for model selection. The final test
    # metrics report once on data that neither CV nor the release gate touched.
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.25, random_state=42
    )

    pipeline = build_pipeline(min_samples_leaf=min_samples_leaf)

    # Five independent validation folds make the release gate less dependent on
    # a lucky split. cross_validate clones this pipeline, so the fitted object
    # below remains the exact model that is finally published.
    cv = cross_validate(
        pipeline,
        X_train_val,
        y_train_val,
        cv=5,
        scoring=("neg_mean_absolute_error", "r2"),
    )
    mae_folds = (-cv["test_neg_mean_absolute_error"]).tolist()
    r2_folds = cv["test_r2"].tolist()
    cv_metrics = {
        "mae_mean": float(np.mean(mae_folds)),
        "mae_std": float(np.std(mae_folds)),
        "r2_mean": float(np.mean(r2_folds)),
        "r2_std": float(np.std(r2_folds)),
        "mae_folds": mae_folds,
        "r2_folds": r2_folds,
    }

    # The published artifact is fitted only on the training partition. Its
    # validation and test metrics therefore describe the exact saved object.
    pipeline.fit(X_train, y_train)
    train_metrics = _compute_metrics(y_train, pipeline.predict(X_train))
    val_metrics = _compute_metrics(y_val, pipeline.predict(X_val))
    test_metrics = _compute_metrics(y_test, pipeline.predict(X_test))

    return pipeline, {
        "train": train_metrics,
        "val": val_metrics,
        "cv": cv_metrics,
        "test_final": test_metrics,
    }, dataset


if __name__ == "__main__":
    # Keep the former entrypoint as a compatibility alias, but require the
    # explicit release CLI rather than silently choosing a repo-relative CSV.
    from mental_health.models.release import main

    raise SystemExit(main())
