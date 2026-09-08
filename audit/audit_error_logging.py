"""Trigger a real server-side 500 and prove its JSON event can be correlated.

Run from the repository root:
    uv run --frozen python audit/audit_error_logging.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

import joblib
import pandas
import sklearn

from audit_serving import VALID, free_port, get, stop_server
from error_artifact_fixture import CrashingPipeline
from mental_health.data.schema import FEATURE_SCHEMA_VERSION
from mental_health.models.artifact_contract import (
    ARTIFACT_CONTRACT_VERSION,
    MANIFEST_FILENAME,
    METADATA_FILENAME,
    MODEL_FILENAME,
    describe_file,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = ROOT / "runtime" / "error-audit.sqlite3"
DEFAULT_SERVER_LOG_PATH = ROOT / "runtime" / "error-audit.stderr.log"
DEFAULT_REPORT_PATH = ROOT / "audit" / "REPORT_error_logging.md"
OUT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_crashing_artifact(artifacts_root: Path) -> Path:
    """Create a complete, verifier-compatible temporary artifact for this audit."""
    version = "error-audit-v1"
    artifact_dir = artifacts_root / version
    artifact_dir.mkdir(parents=True)
    model_path = artifact_dir / MODEL_FILENAME
    metadata_path = artifact_dir / METADATA_FILENAME
    manifest_path = artifact_dir / MANIFEST_FILENAME

    joblib.dump(CrashingPipeline(), model_path)
    model_file = describe_file(model_path)
    metadata = {
        "model_version": version,
        "artifact": {
            "contract_version": ARTIFACT_CONTRACT_VERSION,
            "model_sha256": model_file["sha256"],
        },
        "features": {"schema_version": FEATURE_SCHEMA_VERSION},
        "env": {"sklearn": sklearn.__version__, "pandas": pandas.__version__},
    }
    write_json(metadata_path, metadata)
    write_json(
        manifest_path,
        {
            "contract_version": ARTIFACT_CONTRACT_VERSION,
            "release_id": version,
            "files": {
                MODEL_FILENAME: model_file,
                METADATA_FILENAME: describe_file(metadata_path),
            },
        },
    )
    (artifacts_root / "latest.txt").write_text(version, encoding="utf-8")
    return artifact_dir


def post_with_headers(url: str, payload: dict) -> tuple[int, str, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            return (
                response.status,
                response.read().decode(),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return (
            exc.code,
            exc.read().decode(),
            {key.lower(): value for key, value in exc.headers.items()},
        )
    except Exception as exc:
        return -1, repr(exc), {}


def json_events(server_log_path: Path) -> list[dict]:
    events = []
    for line in server_log_path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def build_parser() -> argparse.ArgumentParser:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run a verified crashing artifact through the real 500 handler."
    )
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--server-log-path", type=Path, default=DEFAULT_SERVER_LOG_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_path = args.log_path.expanduser().resolve()
    server_log_path = args.server_log_path.expanduser().resolve()
    report_path = args.report_path.expanduser().resolve()
    server_log_path.parent.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    failures: list[str] = []

    say("# Structured 500 logging audit")
    say()
    say("- A temporary manifest-verified artifact is used only for this audit.")
    say("- Its pipeline intentionally raises only when POST /predict calls predict().")
    say("- The report records whether a trace exists, not the traceback contents.")
    say()

    with tempfile.TemporaryDirectory(prefix="mental-health-error-audit-") as temp_dir:
        artifacts_root = Path(temp_dir) / "artifacts"
        artifact_dir = build_crashing_artifact(artifacts_root)
        say(f"- Temporary artifact directory: `{artifact_dir}`")

        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join((str(ROOT / "src"), str(ROOT / "audit"))),
            "ARTIFACTS_ROOT": str(artifacts_root),
            "PREDICTION_LOG_PATH": str(log_path),
        }
        server_stderr = server_log_path.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mental_health.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=server_stderr,
        )

        response_status = -1
        response_body = ""
        response_headers: dict[str, str] = {}
        try:
            ready = None
            started_at = time.perf_counter()
            while time.perf_counter() - started_at < 60:
                status_code, body, _ = get(f"{base}/readyz", timeout=1.0)
                if status_code == 200:
                    ready = json.loads(body)
                    break
                if proc.poll() is not None:
                    failures.append(f"Uvicorn exited before ready: {body[:300]}")
                    break
                time.sleep(0.25)

            if ready is None:
                failures.append("The verified crashing artifact did not reach ready state.")
            else:
                say(f"- /readyz returned 200 for temporary version: `{ready['model_version']}`")
                response_status, response_body, response_headers = post_with_headers(
                    f"{base}/predict", VALID
                )
        finally:
            stop_server(proc)
            server_stderr.close()

    request_id = response_headers.get("x-request-id")
    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError:
        response_json = None
    events = json_events(server_log_path)
    error_events = [event for event in events if event.get("event") == "unhandled_exception"]
    event = error_events[-1] if error_events else None

    if response_status != 500:
        failures.append(f"Expected POST /predict to return 500, got {response_status}.")
    if response_json != {"detail": "Internal server error"}:
        failures.append("The client did not receive the expected generic 500 body.")
    if not request_id:
        failures.append("The 500 response did not include X-Request-ID.")
    if "intentional error-audit failure" in response_body:
        failures.append("Internal exception text leaked into the client response.")
    if event is None:
        failures.append("No unhandled_exception JSON event was found in server stderr.")
    else:
        expected = {
            "request_id": request_id,
            "method": "POST",
            "path": "/predict",
            "status_code": 500,
            "exception_type": "RuntimeError",
        }
        for key, value in expected.items():
            if event.get(key) != value:
                failures.append(f"Structured event {key!r} was {event.get(key)!r}, expected {value!r}.")
        if "intentional error-audit failure" not in str(event.get("traceback", "")):
            failures.append("Structured event traceback did not contain the original exception.")

    say()
    say("## Evidence")
    say()
    say(f"- POST /predict status: **{response_status}**")
    say(f"- Generic client body preserved: **{response_json == {'detail': 'Internal server error'}}**")
    say(f"- X-Request-ID returned: `{request_id}`")
    say(f"- JSON event count in server stderr: **{len(events)}**")
    say(f"- unhandled_exception event count: **{len(error_events)}**")
    if event is not None:
        say(f"- Event request ID matches response: **{event.get('request_id') == request_id}**")
        say(f"- Event exception type: `{event.get('exception_type')}`")
        say(f"- Event contains traceback: **{bool(event.get('traceback'))}**")
    say(f"- Server stderr path: `{server_log_path}`")
    say()

    if failures:
        say("## Failed assertions")
        say()
        for failure in failures:
            say(f"- {failure}")
    else:
        say("## Result")
        say()
        say("The real server returned a generic 500 while writing a correlated JSON "
            "event with exception type and traceback to stderr.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"\n>>> wrote {report_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
