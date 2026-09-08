"""Durable local audit records for successful prediction responses."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PREDICTION_LOG_PATH = PROJECT_ROOT / "runtime" / "predictions.sqlite3"
logger = logging.getLogger(__name__)


def resolve_prediction_log_path() -> Path:
    """Return the local database path, optionally overridden for a deployment."""
    configured_path = os.environ.get("PREDICTION_LOG_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_PREDICTION_LOG_PATH


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=5.0)
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_prediction_log(db_path: Path) -> None:
    """Create the local audit table before the API accepts requests."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output REAL NOT NULL,
                model_version TEXT NOT NULL,
                latency_ms REAL NOT NULL CHECK (latency_ms >= 0)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_predictions_timestamp "
            "ON predictions(timestamp)"
        )


def write_prediction(
    db_path: Path,
    *,
    input_payload: Mapping[str, object],
    output: float,
    model_version: str,
    latency_ms: float,
) -> bool:
    """Append one successful prediction without making inference depend on SQLite."""
    try:
        input_json = json.dumps(
            input_payload,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with _connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO predictions (
                    timestamp, input_json, output, model_version, latency_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    input_json,
                    output,
                    model_version,
                    latency_ms,
                ),
            )
    except (OSError, TypeError, ValueError, sqlite3.Error):
        logger.exception("Prediction log write failed for %s", db_path)
        return False
    return True
