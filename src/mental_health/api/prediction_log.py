"""Prediction log — one durable SQLite row per /predict call.

This is an *audit store*, not an application log. Its whole purpose is that a
prediction we served today can be replayed and measured later (which input,
which model version, what did it answer, how long did inference take). If we
never write it down, that measurement is impossible after the fact — the door
closes as time passes.

Design rules baked in here:
  - Fault-isolated: `log_prediction` NEVER raises. A logging failure must not
    turn a successful prediction into a 500. Setup (`init_db`) *may* raise;
    main.py decides what to do with that (same split as the artifact loader).
  - Thread-safe: FastAPI runs our plain `def` routes in a threadpool, so a
    request can land on any worker thread. We therefore open a short-lived
    connection per call (never share one across threads) and run the DB in
    WAL mode so readers never block the single writer.
"""

import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Default DB location: repo root. api/ -> mental_health/ -> src/ -> root = parents[3],
# the same depth save.py and artifacts.py use. Overridable via env in main.py.
DEFAULT_DB_PATH = Path(__file__).parents[3] / "predictions.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id             INTEGER PRIMARY KEY,
    timestamp      TEXT    NOT NULL,
    input_json     TEXT    NOT NULL,
    output         REAL    NOT NULL,
    model_version  TEXT    NOT NULL,
    latency_ms     REAL    NOT NULL
)
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    # Short-lived connection, opened and closed inside one threadpool worker.
    # timeout=5s: if two writers collide, the loser waits instead of erroring.
    conn = sqlite3.connect(db_path, timeout=5.0)
    # WAL persists on the DB file; re-asserting it per connection is a cheap no-op.
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    """Create the predictions table if it does not exist. Call once at startup.

    May raise (e.g. the directory is unwritable). The caller decides whether
    that should block startup — it should not, because logging is auxiliary to
    serving, so main.py catches it.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(db_path)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()


def log_prediction(
    db_path: Path,
    *,
    input_dict: dict,
    output: float,
    model_version: str,
    latency_ms: float,
    timestamp: str | None = None,
) -> None:
    """Write one prediction row. Swallows every error by design — see module docstring."""
    try:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with closing(_connect(db_path)) as conn:
            conn.execute(
                "INSERT INTO predictions "
                "(timestamp, input_json, output, model_version, latency_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    ts,
                    json.dumps(input_dict),
                    float(output),
                    model_version,
                    float(latency_ms),
                ),
            )
            conn.commit()
    except Exception:
        # Never propagate: a broken log must not break a good prediction.
        logger.exception("Failed to write prediction log row")
