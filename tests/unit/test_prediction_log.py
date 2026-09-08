import json
import sqlite3
from datetime import datetime

from mental_health.api.prediction_log import (
    initialize_prediction_log,
    write_prediction,
)


def test_write_prediction_persists_the_served_record(tmp_path):
    db_path = tmp_path / "runtime" / "predictions.sqlite3"
    payload = {"Age": 20, "Country": "India", "Study_Hours": 6.0}

    initialize_prediction_log(db_path)
    written = write_prediction(
        db_path,
        input_payload=payload,
        output=7.25,
        model_version="release-123",
        latency_ms=4.5,
    )

    assert written is True
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT id, timestamp, input_json, output, model_version, latency_ms "
            "FROM predictions"
        ).fetchone()

    assert row[0] == 1
    assert datetime.fromisoformat(row[1]).tzinfo is not None
    assert json.loads(row[2]) == payload
    assert row[3:] == (7.25, "release-123", 4.5)


def test_write_prediction_returns_false_when_sqlite_is_unavailable(tmp_path, caplog):
    db_path = tmp_path / "not-a-database"
    db_path.mkdir()

    written = write_prediction(
        db_path,
        input_payload={"Age": 20},
        output=7.25,
        model_version="release-123",
        latency_ms=4.5,
    )

    assert written is False
    assert "Prediction log write failed" in caplog.text


def test_write_prediction_persists_a_complete_shadow_comparison(tmp_path):
    db_path = tmp_path / "runtime" / "predictions.sqlite3"
    initialize_prediction_log(db_path)

    written = write_prediction(
        db_path,
        input_payload={"Age": 20},
        output=7.25,
        model_version="primary-release",
        latency_ms=4.5,
        shadow_model_version="candidate-release",
        shadow_output=7.5,
        shadow_latency_ms=3.0,
    )

    assert written is True
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT shadow_model_version, shadow_output, shadow_latency_ms "
            "FROM predictions"
        ).fetchone()

    assert row == ("candidate-release", 7.5, 3.0)


def test_initialize_prediction_log_adds_shadow_columns_to_a_legacy_database(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output REAL NOT NULL,
                model_version TEXT NOT NULL,
                latency_ms REAL NOT NULL CHECK (latency_ms >= 0)
            )
            """
        )

    initialize_prediction_log(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(predictions)")}

    assert {"shadow_model_version", "shadow_output", "shadow_latency_ms"} <= columns


def test_write_prediction_rejects_partial_shadow_data(tmp_path, caplog):
    db_path = tmp_path / "predictions.sqlite3"
    initialize_prediction_log(db_path)

    written = write_prediction(
        db_path,
        input_payload={"Age": 20},
        output=7.25,
        model_version="primary-release",
        latency_ms=4.5,
        shadow_model_version="candidate-release",
    )

    assert written is False
    assert "Shadow prediction fields must be supplied together" in caplog.text
