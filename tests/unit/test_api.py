import json
import logging
import sqlite3
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from mental_health.api import main
from mental_health.api.structured_logging import JsonEventFormatter, event_logger


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


class CrashingPipeline:
    def predict(self, rows):
        raise RuntimeError("secret internal failure")


class ShadowPipeline:
    def predict(self, rows):
        assert list(rows.columns) == list(VALID_PAYLOAD)
        assert len(rows) == 1
        return [6.75]


class JsonRecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(self.format(record))


def fake_load_latest_artifact() -> dict:
    return {
        "pipeline": FakePipeline(),
        "metadata": {},
        "version": "test-version",
        "path": "fake-path",
    }


def fake_load_latest_artifact_failure() -> dict:
    raise main.ArtifactLoadError("boom")


def fake_load_crashing_artifact() -> dict:
    return {
        "pipeline": CrashingPipeline(),
        "metadata": {},
        "version": "test-version",
        "path": "fake-path",
    }


def fake_load_primary_and_shadow(artifacts_root=None) -> dict:
    if artifacts_root is None:
        return fake_load_latest_artifact()
    return {
        "pipeline": ShadowPipeline(),
        "metadata": {},
        "version": "shadow-version",
        "path": "shadow-path",
    }


def fake_load_primary_and_crashing_shadow(artifacts_root=None) -> dict:
    if artifacts_root is None:
        return fake_load_latest_artifact()
    return {
        "pipeline": CrashingPipeline(),
        "metadata": {},
        "version": "shadow-version",
        "path": "shadow-path",
    }


def fake_load_primary_with_unavailable_shadow(artifacts_root=None) -> dict:
    if artifacts_root is None:
        return fake_load_latest_artifact()
    raise main.ArtifactLoadError("candidate artifact is broken")


@pytest.fixture(autouse=True)
def prediction_log_path(monkeypatch, tmp_path):
    path = tmp_path / "predictions.sqlite3"
    monkeypatch.setattr(main, "resolve_prediction_log_path", lambda: path)
    return path


def test_healthz_returns_ok():
    with TestClient(main.app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert UUID(response.headers[main.REQUEST_ID_HEADER]).hex == response.headers[
        main.REQUEST_ID_HEADER
    ]


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


def test_predict_persists_the_served_request(monkeypatch, prediction_log_path):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 200
    with sqlite3.connect(prediction_log_path) as connection:
        row = connection.execute(
            "SELECT input_json, output, model_version, latency_ms FROM predictions"
        ).fetchone()

    assert json.loads(row[0]) == VALID_PAYLOAD
    assert row[1] == 7.25
    assert row[2] == "test-version"
    assert row[3] >= 0


def test_predict_remains_available_when_prediction_logging_fails(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact)
    monkeypatch.setattr(main, "write_prediction", lambda *args, **kwargs: False)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["mental_health_score"] == 7.25


def test_predict_returns_primary_response_and_logs_shadow_result(
    monkeypatch, prediction_log_path, tmp_path
):
    monkeypatch.setenv("SHADOW_ARTIFACTS_ROOT", str(tmp_path / "shadow-artifacts"))
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_primary_and_shadow)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["mental_health_score"] == 7.25
    assert response.json()["model_version"] == "test-version"
    assert "shadow_output" not in response.json()
    with sqlite3.connect(prediction_log_path) as connection:
        row = connection.execute(
            "SELECT output, model_version, shadow_output, shadow_model_version, "
            "shadow_latency_ms FROM predictions"
        ).fetchone()

    assert row[0:4] == (7.25, "test-version", 6.75, "shadow-version")
    assert row[4] >= 0


def test_predict_remains_available_when_shadow_pipeline_crashes(
    monkeypatch, prediction_log_path, tmp_path
):
    monkeypatch.setenv("SHADOW_ARTIFACTS_ROOT", str(tmp_path / "shadow-artifacts"))
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_primary_and_crashing_shadow)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["mental_health_score"] == 7.25
    with sqlite3.connect(prediction_log_path) as connection:
        row = connection.execute(
            "SELECT shadow_output, shadow_model_version, shadow_latency_ms FROM predictions"
        ).fetchone()

    assert row == (None, None, None)


def test_primary_stays_ready_when_the_optional_shadow_artifact_cannot_load(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SHADOW_ARTIFACTS_ROOT", str(tmp_path / "shadow-artifacts"))
    monkeypatch.setattr(
        main,
        "load_latest_artifact",
        fake_load_primary_with_unavailable_shadow,
    )

    with TestClient(main.app) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["model_version"] == "test-version"


def test_predict_rejects_target_in_request(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact)
    payload = {**VALID_PAYLOAD, "Mental_Health_Score": 8.0}

    with TestClient(main.app) as client:
        response = client.post("/predict", json=payload)

    assert response.status_code == 422


def test_readyz_returns_503_when_artifact_fails(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact_failure)

    with TestClient(main.app) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "boom",
    }


def test_predict_returns_clean_500_when_pipeline_crashes(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_crashing_artifact)

    with TestClient(main.app, raise_server_exceptions=False) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "secret internal failure" not in response.text


def test_predict_logs_a_structured_correlated_500_event(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_crashing_artifact)
    handler = JsonRecordingHandler()
    handler.setFormatter(JsonEventFormatter())
    event_logger.addHandler(handler)

    try:
        with TestClient(main.app, raise_server_exceptions=False) as client:
            response = client.post("/predict", json=VALID_PAYLOAD)
    finally:
        event_logger.removeHandler(handler)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    request_id = response.headers[main.REQUEST_ID_HEADER]
    assert UUID(request_id).hex == request_id
    assert "secret internal failure" not in response.text

    assert len(handler.messages) == 1
    event = json.loads(handler.messages[0])
    assert event["event"] == "unhandled_exception"
    assert event["request_id"] == request_id
    assert event["method"] == "POST"
    assert event["path"] == "/predict"
    assert event["status_code"] == 500
    assert event["exception_type"] == "RuntimeError"
    assert "secret internal failure" in event["traceback"]


def test_predict_returns_503_when_artifact_fails(monkeypatch):
    monkeypatch.setattr(main, "load_latest_artifact", fake_load_latest_artifact_failure)

    with TestClient(main.app) as client:
        response = client.post("/predict", json=VALID_PAYLOAD)

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "reason": "boom",
    }
