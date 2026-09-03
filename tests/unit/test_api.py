from fastapi.testclient import TestClient

from mental_health.api import main


VALID_PAYLOAD = {
    "Age": 20,
    "Gender": "Male",
    "Country": "India",
    "Academic_Level": "Undergraduate",
    "Most_Used_Platform": "Instagram",
    "Purpose_Of_Use": "Education",
    "Avg_Daily_Usage_Hours": 3.0,
    "Daily_Unlocks": 80,
    "Study_Hours": 6.0,
    "Physical_Activity_Hours": 1.0,
    "Sleep_Hours_Per_Night": 8.0,
    "Stress_Level": "Medium",
}


class FakePipeline:
    def predict(self, rows):
        assert list(rows.columns) == list(VALID_PAYLOAD)
        assert len(rows) == 1
        return [7.25]


def fake_load_latest_artifact() -> dict:
    return {
        "pipeline": FakePipeline(),
        "metadata": {},
        "version": "test-version",
        "path": "fake-path",
    }


def fake_load_latest_artifact_failure() -> dict:
    raise main.ArtifactLoadError("boom")


def test_healthz_returns_ok():
    with TestClient(main.app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_ready_when_artifact_loads(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact)

    with TestClient(main.app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "model_version": "test-version",
    }


def test_predict_returns_prediction_for_valid_payload(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["mental_health_score"] == 7.25
    assert body["model_version"] == "test-version"
    assert body["note"]


def test_readyz_returns_503_when_artifact_fails(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact_failure)

    with TestClient(main.app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "boom",
    }


def test_predict_returns_503_when_artifact_fails(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact_failure)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "boom",
    }
