"""Serving-layer audit: cold start, input validation behaviour, and real latency.

Run from repo root:   uv run python audit/audit_serving.py
Writes:               audit/REPORT_serving.md

Boots uvicorn on a spare port, measures it, shuts it down. Read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
OUT: list[str] = []

VALID = {
    "Age": 20, "Gender": "Male", "Country": "India",
    "Academic_Level": "Undergraduate", "Most_Used_Platform": "Instagram",
    "Purpose_Of_Use": "Education", "Avg_Daily_Usage_Hours": 3.0,
    "Daily_Unlocks": 80, "Study_Hours": 6.0,
    "Physical_Activity_Hours": 1.0, "Sleep_Hours_Per_Night": 8.0,
    "Stress_Level": "Medium",
}


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(url: str, payload: dict, timeout: float = 20.0):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode(), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.perf_counter() - t0
    except Exception as e:
        return -1, repr(e), time.perf_counter() - t0


def get(url: str, timeout: float = 5.0):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode(), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), time.perf_counter() - t0
    except Exception as e:
        return -1, repr(e), time.perf_counter() - t0


# ----------------------------------------------------------------------------
# input validation probes
# ----------------------------------------------------------------------------
PROBES = [
    ("valid baseline request", VALID, "200 with a score"),
    ("unknown field added", {**VALID, "Hacker": 1}, "422 — extra='forbid' is set"),
    ("Age below range (12)", {**VALID, "Age": 12}, "422 — Field(ge=13)"),
    ("Age as string '20'", {**VALID, "Age": "20"}, "pydantic v2 coerces -> 200"),
    ("Gender not in vocabulary", {**VALID, "Gender": "Other"},
     "422 — closed vocabulary. NOTE: this is a real user your API cannot serve."),
    ("unseen Country 'Wakanda'", {**VALID, "Country": "Wakanda"},
     "200 - preprocessing collapses it into the explicit Other bucket"),
    ("time budget violated (sum>24)",
     {**VALID, "Sleep_Hours_Per_Night": 12.0, "Study_Hours": 12.0,
      "Avg_Daily_Usage_Hours": 6.0, "Physical_Activity_Hours": 4.0},
     "422 — cross-field model_validator"),
    ("missing required field", {k: v for k, v in VALID.items() if k != "Sleep_Hours_Per_Night"},
     "422"),
    ("null in a required field", {**VALID, "Study_Hours": None}, "422"),
    ("negative usage hours", {**VALID, "Avg_Daily_Usage_Hours": -5.0}, "422 — Field(ge=0)"),
    ("extreme-but-legal input", {**VALID, "Avg_Daily_Usage_Hours": 16.0,
                                 "Sleep_Hours_Per_Night": 0.0, "Study_Hours": 0.0,
                                 "Physical_Activity_Hours": 0.0},
     "200 — far outside training support, yet returned with no uncertainty signal"),
]


def section_probes(base: str) -> int:
    say("## Input validation behaviour")
    say()
    say("| probe | status | expectation | response (truncated) |")
    say("|---|---|---|---|")
    successful_predictions = 0
    for name, payload, expect in PROBES:
        st, body, _ = post(f"{base}/predict", payload)
        if st == 200:
            successful_predictions += 1
        body = body.replace("|", "\\|").replace("\n", " ")[:110]
        say(f"| {name} | **{st}** | {expect} | `{body}` |")
    say()
    say("> Two rows deserve attention regardless of what they return. An unseen "
        "country is collapsed into the explicit Other bucket and scored as if it were "
        "known — the caller is never told the input was out of vocabulary. And the "
        "extreme-but-legal row is scored with the same confidence as a typical one, "
        "because a point prediction carries no uncertainty. Neither is a crash; both "
        "are things you should be able to describe out loud.")
    say()
    return successful_predictions


# ----------------------------------------------------------------------------
# closed-loop load
# ----------------------------------------------------------------------------
def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def load_level(base: str, concurrency: int, seconds: float):
    stop = time.perf_counter() + seconds
    lat: list[float] = []
    errs = 0

    def worker():
        nonlocal errs
        local: list[float] = []
        while time.perf_counter() < stop:
            st, _, dt = post(f"{base}/predict", VALID)
            if st != 200:
                errs += 1
            local.append(dt)
        return local

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for chunk in ex.map(lambda _: worker(), range(concurrency)):
            lat.extend(chunk)
    wall = time.perf_counter() - t0
    return {
        "concurrency": concurrency, "requests": len(lat), "errors": errs,
        "rps": len(lat) / wall,
        "p50": pct(lat, 50) * 1000, "p95": pct(lat, 95) * 1000,
        "p99": pct(lat, 99) * 1000, "max": max(lat) * 1000,
        "mean": statistics.mean(lat) * 1000,
    }


def section_load(base: str, duration: float, workers: int) -> list[dict]:
    say("## Latency and throughput")
    say()
    say(f"Closed-loop, {duration:.0f}s per level, {workers} uvicorn worker(s), "
        f"{os.cpu_count()} logical CPUs on this machine. Latency in milliseconds.")
    say()
    say("| concurrency | requests | errors | RPS | mean | p50 | p95 | p99 | max |")
    say("|---|---|---|---|---|---|---|---|---|")
    rows = []
    for c in (1, 4, 16, 64):
        r = load_level(base, c, duration)
        rows.append(r)
        say(f"| {r['concurrency']} | {r['requests']} | {r['errors']} | "
            f"**{r['rps']:.1f}** | {r['mean']:.1f} | {r['p50']:.1f} | "
            f"**{r['p95']:.1f}** | {r['p99']:.1f} | {r['max']:.1f} |")
    say()
    best = max(rows, key=lambda r: r["rps"])
    say(f"- Peak throughput observed: **{best['rps']:.1f} req/s** at concurrency "
        f"{best['concurrency']}, p95 **{best['p95']:.1f} ms**.")
    say("- These are the only numbers that let you write the word *scale* on a resume. "
        "Whatever they are, they are yours and you can defend them.")
    say()
    say("> `predict` is a sync `def`, so Starlette runs it in a threadpool; the model "
        "is `n_jobs=1`, and a one-row DataFrame is constructed per call. If RPS stops "
        "rising while p95 climbs, you have found the saturation point — that is the "
        "sentence worth having, not a round number you guessed.")
    say()
    return rows


def latest_prediction_id(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute("SELECT MAX(id) FROM predictions").fetchone()
    except sqlite3.Error:
        return 0
    return row[0] or 0


def prediction_log_count(db_path: Path, previous_id: int) -> int | None:
    try:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM predictions WHERE id > ?", (previous_id,)
            ).fetchone()
    except sqlite3.Error:
        return None
    return row[0]


def section_prediction_log(
    db_path: Path, expected_count: int, captured_count: int | None
) -> None:
    say("## Prediction log evidence")
    say()
    say(f"- SQLite path: `{db_path}`")
    if captured_count is None:
        say("- Could not query the SQLite prediction log after the run.")
    else:
        say(f"- Successful prediction responses in this audit: **{expected_count}**")
        say(f"- New SQLite records captured in this audit: **{captured_count}**")
        if captured_count == expected_count:
            say("- Record count matched successful responses exactly.")
        else:
            say("- Record count did not match successful responses; investigate before "
                "treating this as an audit trail.")
    say()


def section_server_stderr(server_log_path: Path) -> None:
    say("## Server stderr evidence")
    say()
    say(f"- Server stderr path: `{server_log_path}`")
    try:
        text = server_log_path.read_text(encoding="utf-8")
    except OSError as exc:
        say(f"- Could not read server stderr: `{exc}`")
    else:
        write_failures = text.count("Prediction log write failed")
        say(f"- Prediction-log write failures recorded by the server: **{write_failures}**")
        say("- Stderr is written to a file instead of an unread subprocess pipe so "
            "error output cannot block worker processes during the load test.")
    say()


def section_ops_surface() -> None:
    say("## Ops surface")
    say()
    checks = [
        ("Dockerfile", ROOT / "Dockerfile", "code-only image can be built and tested in CI"),
        ("docker-compose.yml", ROOT / "docker-compose.yml", "no local multi-service stack"),
        (".dockerignore", ROOT / ".dockerignore", "build context excludes raw data and artifacts"),
        ("CI workflow", ROOT / ".github" / "workflows", "tests and image build run on push and pull requests"),
        ("Makefile / task runner", ROOT / "Makefile", "documents host training, test, and container serving"),
        ("/metrics endpoint", None, "no Prometheus scrape target"),
        ("structured request logging", ROOT / "src" / "mental_health" / "api" /
         "structured_logging.py", "unhandled 500 events emit correlated JSON to stderr"),
        ("prediction log / audit trail", ROOT / "src" / "mental_health" / "api" /
         "prediction_log.py", "local SQLite records successful predictions"),
        ("drift monitoring", None, "nothing to compare against a baseline"),
        ("load test in repo", ROOT / "audit" / "audit_serving.py",
         "closed-loop request measurements are reproducible"),
    ]
    say("| artifact | present | notes |")
    say("|---|---|---|")
    for name, path, why in checks:
        present = "yes" if (path and path.exists()) else "**no**"
        say(f"| {name} | {present} | {why} |")
    say()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure one local Uvicorn worker configuration."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of Uvicorn worker processes to start (default: 1).",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Seconds per concurrency level (default: AUDIT_SECONDS or 8).",
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=None,
        help="SQLite path for this audit run (default: separate path per worker count).",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Markdown output path (default: separate report per worker count).",
    )
    parser.add_argument(
        "--server-log-path",
        type=Path,
        default=None,
        help="Server stderr path (default: separate ignored file per worker count).",
    )
    return parser


def _default_log_path(workers: int) -> Path:
    return ROOT / "runtime" / f"serving-audit-workers-{workers}.sqlite3"


def _default_report_path(workers: int) -> Path:
    if workers == 1:
        return ROOT / "audit" / "REPORT_serving.md"
    return ROOT / "audit" / f"REPORT_serving-workers-{workers}.md"


def _default_server_log_path(workers: int) -> Path:
    return ROOT / "runtime" / f"serving-audit-workers-{workers}.stderr.log"


def stop_server(proc: subprocess.Popen) -> None:
    """Stop the Uvicorn supervisor and every worker it started.

    On Windows, terminating only the supervisor leaves spawned worker processes
    alive. Those workers consume CPU and contaminate the next benchmark.
    """
    if proc.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.terminate()

    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")

    duration = args.seconds if args.seconds is not None else float(
        os.environ.get("AUDIT_SECONDS", "8")
    )
    if duration <= 0:
        raise SystemExit("--seconds must be greater than 0")

    workers = args.workers
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log_path = (args.log_path or _default_log_path(workers)).expanduser().resolve()
    report_path = (args.report_path or _default_report_path(workers)).expanduser().resolve()
    server_log_path = (
        args.server_log_path or _default_server_log_path(workers)
    ).expanduser().resolve()
    previous_log_id = latest_prediction_id(log_path)
    probe_successes = 0
    load_rows: list[dict] = []

    say("# Serving audit")
    say()
    say(f"- Uvicorn worker processes requested: **{workers}**")
    say()
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PREDICTION_LOG_PATH": str(log_path),
    }
    t0 = time.perf_counter()
    server_log_path.parent.mkdir(parents=True, exist_ok=True)
    server_stderr = server_log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mental_health.api.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
         "--workers", str(workers)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=server_stderr)

    ready_at = None
    try:
        while time.perf_counter() - t0 < 60:
            st, body, _ = get(f"{base}/readyz", timeout=1.0)
            if st == 200:
                ready_at = time.perf_counter() - t0
                break
            if st == 503:
                say(f"`/readyz` returned 503 — model did not load: `{body[:200]}`")
                say()
                break
            if proc.poll() is not None:
                say("uvicorn exited before becoming ready. stderr:")
                say("```")
                server_stderr.flush()
                say(server_log_path.read_text(encoding="utf-8")[-2000:])
                say("```")
                break
            time.sleep(0.25)

        if ready_at is None:
            say("Server never reported ready — aborting the measured sections.")
        else:
            say("## Cold start")
            say()
            say(f"- process spawn -> `/readyz` 200: **{ready_at * 1000:.0f} ms** "
                "(includes interpreter boot, sklearn import, and `joblib.load`)")
            hz = get(f"{base}/healthz")
            rz = get(f"{base}/readyz")
            say(f"- `/healthz` -> {hz[0]} in {hz[2] * 1000:.1f} ms")
            say(f"- `/readyz`  -> {rz[0]} in {rz[2] * 1000:.1f} ms  `{rz[1][:120]}`")
            say()
            say("> The liveness/readiness split here is correct and worth saying out "
                "loud in an interview: `/healthz` answers *is the process up*, "
                "`/readyz` answers *can it serve*, and a missing artifact yields 503 "
                "rather than a crash loop. Most student projects have one `/health` "
                "that returns 200 unconditionally.")
            say()
            probe_successes = section_probes(base)
            load_rows = section_load(base, duration, workers)
    finally:
        stop_server(proc)
        server_stderr.close()

    expected_log_count = probe_successes + sum(
        row["requests"] - row["errors"] for row in load_rows
    )
    section_prediction_log(
        log_path,
        expected_log_count,
        prediction_log_count(log_path, previous_log_id),
    )
    section_server_stderr(server_log_path)
    section_ops_surface()
    report_path.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n>>> wrote {report_path}")


if __name__ == "__main__":
    main()
