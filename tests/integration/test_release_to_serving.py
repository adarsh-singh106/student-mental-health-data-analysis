"""A real release test: generated CSV -> trained artifact -> HTTP prediction."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from mental_health.api import main
from mental_health.api.artifacts import load_latest_artifact
from mental_health.data.schema import TARGET_COLUMN
from mental_health.models.release import release


def _write_learnable_dataset(path: Path) -> dict:
    """Create valid rows with a deterministic target the pipeline can learn.

    This is test data, not a claim about the real domain. Its only job is to
    exercise the complete release contract without depending on the unlicensed
    raw CSV that a clean clone deliberately does not contain.
    """
    stress_scores = {
        "Low": 8.5,
        "Medium": 7.0,
        "High": 5.5,
        "Very High": 4.0,
    }
    stress_levels = list(stress_scores)
    rows = []

    for index in range(120):
        stress_level = stress_levels[index % len(stress_levels)]
        rows.append(
            {
                "Age": 18 + (index % 7),
                "Gender": "Male" if index % 2 else "Female",
                "Country": ["India", "USA", "Canada", "Other"][index % 4],
                "Academic_Level": ["High School", "Undergraduate", "Graduate"][index % 3],
                "Most_Used_Platform": ["Instagram", "YouTube", "WhatsApp"][index % 3],
                "Purpose_Of_Use": ["Education", "Entertainment", "News", "Networking"][index % 4],
                "Avg_Daily_Usage_Hours": 1.0 + (index % 8) * 0.5,
                "Daily_Unlocks": 30 + (index % 70),
                "Study_Hours": 2.0 + (index % 5) * 0.5,
                "Physical_Activity_Hours": 0.5 + (index % 3) * 0.25,
                "Sleep_Hours_Per_Night": 7.0 + (index % 3) * 0.25,
                "Stress_Level": stress_level,
                TARGET_COLUMN: stress_scores[stress_level],
            }
        )

    pd.DataFrame(rows).to_csv(path, index=False)
    return rows[0]


def test_release_trains_and_serves_a_verified_artifact(tmp_path, monkeypatch):
    data_path = tmp_path / "release-input.csv"
    request_row = _write_learnable_dataset(data_path)
    artifacts_root = tmp_path / "artifacts"

    # Git cleanliness is a production release requirement. The isolated test
    # substitutes a known source revision so it does not depend on this checkout.
    monkeypatch.setattr("mental_health.models.save._git_dirty", lambda: False)
    monkeypatch.setattr("mental_health.models.save._git_commit", lambda: "test-commit")

    saved = release(data_path, artifacts_root)
    loaded = load_latest_artifact(artifacts_root)

    assert loaded["integrity_verified"] is True
    assert loaded["version"] == saved.version
    assert loaded["metadata"]["dataset"]["sha256"]
    assert loaded["metadata"]["features"]["schema_version"] == "1.0.0"

    monkeypatch.setattr(main, "load_latest_artifact", lambda: load_latest_artifact(artifacts_root))
    payload = {key: value for key, value in request_row.items() if key != TARGET_COLUMN}

    with TestClient(main.app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == saved.version
    assert 0 <= body["mental_health_score"] <= 10
