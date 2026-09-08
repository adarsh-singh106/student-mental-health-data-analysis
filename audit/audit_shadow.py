"""Prove an optional shadow artifact is evaluated without changing API responses.

Run from the repository root after a clean-provenance candidate exists:
    uv run --frozen python audit/audit_shadow.py
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

from audit_serving import free_port, get, post, stop_server


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHADOW_ROOT = ROOT / "runtime" / "shadow-artifacts"
DEFAULT_LOG_PATH = ROOT / "runtime" / "shadow-audit.sqlite3"
DEFAULT_SERVER_LOG_PATH = ROOT / "runtime" / "shadow-audit.stderr.log"
DEFAULT_REPORT_PATH = ROOT / "audit" / "REPORT_shadow.md"
OUT: list[str] = []

PLATFORMS = (
    "Facebook", "Instagram", "Snapchat", "Twitter", "YouTube", "TikTok",
    "LinkedIn", "WhatsApp", "WeChat", "VKontakte", "KakaoTalk", "LINE",
)
COUNTRIES = (
    "India", "USA", "Canada", "France", "Germany", "UK", "Turkey", "Spain",
    "Mexico", "Ireland", "Australia", "Other",
)
PURPOSES = ("Networking", "Education", "Entertainment", "News")
STRESS_LEVELS = ("Low", "Medium", "High", "Very High")


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def latest_prediction_id(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT MAX(id) FROM predictions").fetchone()
    except sqlite3.Error:
        return 0
    return row[0] or 0


def payload_for(index: int) -> dict[str, object]:
    """Create deterministic, valid, varied requests without using the source CSV."""
    return {
        "Age": 18 + (index % 7),
        "Gender": ("Male", "Female")[index % 2],
        "Country": COUNTRIES[index % len(COUNTRIES)],
        "Academic_Level": (
            "High School", "Undergraduate", "Graduate"
        )[index % 3],
        "Most_Used_Platform": PLATFORMS[index % len(PLATFORMS)],
        "Purpose_Of_Use": PURPOSES[index % len(PURPOSES)],
        "Avg_Daily_Usage_Hours": 1.0 + (index % 5) * 0.75,
        "Daily_Unlocks": 25 + (index % 125),
        "Study_Hours": 4.0 + (index % 3),
        "Physical_Activity_Hours": 1.0 + (index % 3) * 0.5,
        "Sleep_Hours_Per_Night": 7.0 + (index % 2),
        "Stress_Level": STRESS_LEVELS[index % len(STRESS_LEVELS)],
    }


def query_comparison(db_path: Path, previous_id: int) -> dict[str, object]:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*),
                COUNT(shadow_output),
                AVG(ABS(output - shadow_output)),
                MAX(ABS(output - shadow_output)),
                AVG(latency_ms),
                AVG(shadow_latency_ms)
            FROM predictions
            WHERE id > ?
            """,
            (previous_id,),
        ).fetchone()
        versions = [
            value[0]
            for value in connection.execute(
                """
                SELECT DISTINCT shadow_model_version
                FROM predictions
                WHERE id > ? AND shadow_model_version IS NOT NULL
                ORDER BY shadow_model_version
                """,
                (previous_id,),
            )
        ]
    return {
        "rows": row[0],
        "shadow_rows": row[1],
        "mean_absolute_difference": row[2],
        "max_absolute_difference": row[3],
        "mean_primary_latency_ms": row[4],
        "mean_shadow_latency_ms": row[5],
        "shadow_versions": versions,
    }


def format_metric(value: object, places: int = 6) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.{places}f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a real primary-plus-shadow inference comparison."
    )
    parser.add_argument("--shadow-artifacts-root", type=Path, default=DEFAULT_SHADOW_ROOT)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--server-log-path", type=Path, default=DEFAULT_SERVER_LOG_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--requests", type=int, default=500)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.requests < 1:
        raise SystemExit("--requests must be at least 1")

    shadow_root = args.shadow_artifacts_root.expanduser().resolve()
    log_path = args.log_path.expanduser().resolve()
    server_log_path = args.server_log_path.expanduser().resolve()
    report_path = args.report_path.expanduser().resolve()
    if not (shadow_root / "latest.txt").is_file():
        raise SystemExit(f"Shadow artifact pointer does not exist: {shadow_root / 'latest.txt'}")

    port = free_port()
    base = f"http://127.0.0.1:{port}"
    previous_id = latest_prediction_id(log_path)
    server_log_path.parent.mkdir(parents=True, exist_ok=True)

    say("# Shadow-serving audit")
    say()
    say(f"- Primary artifact root: `{ROOT / 'artifacts'}`")
    say(f"- Shadow artifact root: `{shadow_root}`")
    say(f"- Requests planned: **{args.requests}**")
    say("- The public API remains configured to return only the primary artifact result.")
    say()

    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PREDICTION_LOG_PATH": str(log_path),
        "SHADOW_ARTIFACTS_ROOT": str(shadow_root),
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

    ready_body: dict[str, object] | None = None
    failures: list[str] = []
    successful_responses = 0
    t0 = time.perf_counter()
    try:
        while time.perf_counter() - t0 < 60:
            status_code, body, _ = get(f"{base}/readyz", timeout=1.0)
            if status_code == 200:
                ready_body = json.loads(body)
                break
            if proc.poll() is not None:
                failures.append(f"Uvicorn exited before ready: {body[:300]}")
                break
            time.sleep(0.25)

        if ready_body is None:
            failures.append("Primary service did not report ready within 60 seconds.")
        else:
            primary_version = ready_body["model_version"]
            say(f"- Primary /readyz version: `{primary_version}`")
            for index in range(args.requests):
                status_code, body, _ = post(f"{base}/predict", payload_for(index))
                if status_code != 200:
                    failures.append(
                        f"Request {index} returned {status_code}: {body[:250]}"
                    )
                    continue
                response = json.loads(body)
                if response.get("model_version") != primary_version:
                    failures.append(
                        f"Request {index} exposed a non-primary model version: {response}"
                    )
                if any(key.startswith("shadow_") for key in response):
                    failures.append(f"Request {index} leaked shadow data: {response}")
                successful_responses += 1
    finally:
        stop_server(proc)
        server_stderr.close()

    comparison: dict[str, object] | None = None
    try:
        comparison = query_comparison(log_path, previous_id)
    except sqlite3.Error as exc:
        failures.append(f"Could not query shadow comparison records: {exc}")

    say()
    say("## Evidence")
    say()
    say(f"- Successful HTTP responses: **{successful_responses}**")
    say(f"- Failures detected before log comparison: **{len(failures)}**")
    if comparison is not None:
        say(f"- New prediction-log rows: **{comparison['rows']}**")
        say(f"- Rows with both primary and shadow scores: **{comparison['shadow_rows']}**")
        say(f"- Shadow artifact version(s) observed: `{comparison['shadow_versions']}`")
        say(
            "- Mean absolute primary-shadow score difference: "
            f"**{format_metric(comparison['mean_absolute_difference'])}**"
        )
        say(
            "- Maximum absolute primary-shadow score difference: "
            f"**{format_metric(comparison['max_absolute_difference'])}**"
        )
        say(
            "- Mean logged model-path latency, primary/shadow: "
            f"**{format_metric(comparison['mean_primary_latency_ms'], 3)} ms / "
            f"{format_metric(comparison['mean_shadow_latency_ms'], 3)} ms**"
        )

        if comparison["rows"] != successful_responses:
            failures.append("Successful responses did not match persisted prediction-log rows.")
        if comparison["shadow_rows"] != successful_responses:
            failures.append("Not every successful response retained a shadow comparison.")

    stderr_text = server_log_path.read_text(encoding="utf-8")
    shadow_failures = stderr_text.count("Shadow prediction failed")
    say(f"- Shadow prediction failures in server stderr: **{shadow_failures}**")
    say(f"- Server stderr path: `{server_log_path}`")
    say()

    if failures:
        say("## Failed assertions")
        say()
        for failure in failures[:20]:
            say(f"- {failure}")
        if len(failures) > 20:
            say(f"- ... plus {len(failures) - 20} additional failures")
    else:
        say("## Result")
        say()
        say("All responses retained the primary public contract, and every persisted "
            "successful request carried a candidate comparison.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"\n>>> wrote {report_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
