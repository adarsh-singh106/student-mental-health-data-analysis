# Serving audit

- Uvicorn worker processes requested: **4**

## Cold start

- process spawn -> `/readyz` 200: **3054 ms** (includes interpreter boot, sklearn import, and `joblib.load`)
- `/healthz` -> 200 in 33.6 ms
- `/readyz`  -> 200 in 9.0 ms  `{"status":"ready","model_version":"20260908T061824666806Z-4888d94c"}`

> The liveness/readiness split here is correct and worth saying out loud in an interview: `/healthz` answers *is the process up*, `/readyz` answers *can it serve*, and a missing artifact yields 503 rather than a crash loop. Most student projects have one `/health` that returns 200 unconditionally.

## Input validation behaviour

| probe | status | expectation | response (truncated) |
|---|---|---|---|
| valid baseline request | **200** | 200 with a score | `{"mental_health_score":7.6839999999999975,"model_version":"20260908T061824666806Z-4888d94c","note":"Educationa` |
| unknown field added | **422** | 422 — extra='forbid' is set | `{"detail":[{"type":"extra_forbidden","loc":["body","Hacker"],"msg":"Extra inputs are not permitted","input":1}` |
| Age below range (12) | **422** | 422 — Field(ge=13) | `{"detail":[{"type":"greater_than_equal","loc":["body","Age"],"msg":"Input should be greater than or equal to 1` |
| Age as string '20' | **200** | pydantic v2 coerces -> 200 | `{"mental_health_score":7.6839999999999975,"model_version":"20260908T061824666806Z-4888d94c","note":"Educationa` |
| Gender not in vocabulary | **422** | 422 — closed vocabulary. NOTE: this is a real user your API cannot serve. | `{"detail":[{"type":"value_error","loc":["body","Gender"],"msg":"Value error, Gender must be one of: Male, Fema` |
| unseen Country 'Wakanda' | **200** | 200 - preprocessing collapses it into the explicit Other bucket | `{"mental_health_score":7.876999999999999,"model_version":"20260908T061824666806Z-4888d94c","note":"Educational` |
| time budget violated (sum>24) | **422** | 422 — cross-field model_validator | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, Avg_Daily_Usage_Hours + Study_Hours + Phys` |
| missing required field | **422** | 422 | `{"detail":[{"type":"missing","loc":["body","Sleep_Hours_Per_Night"],"msg":"Field required","input":{"Age":20,"` |
| null in a required field | **422** | 422 | `{"detail":[{"type":"float_type","loc":["body","Study_Hours"],"msg":"Input should be a valid number","input":nu` |
| negative usage hours | **422** | 422 — Field(ge=0) | `{"detail":[{"type":"greater_than_equal","loc":["body","Avg_Daily_Usage_Hours"],"msg":"Input should be greater ` |
| extreme-but-legal input | **200** | 200 — far outside training support, yet returned with no uncertainty signal | `{"mental_health_score":4.9460000000000015,"model_version":"20260908T061824666806Z-4888d94c","note":"Educationa` |

> Two rows deserve attention regardless of what they return. An unseen country is collapsed into the explicit Other bucket and scored as if it were known — the caller is never told the input was out of vocabulary. And the extreme-but-legal row is scored with the same confidence as a typical one, because a point prediction carries no uncertainty. Neither is a crash; both are things you should be able to describe out loud.

## Latency and throughput

Closed-loop, 8s per level, 4 uvicorn worker(s), 16 logical CPUs on this machine. Latency in milliseconds.

| concurrency | requests | errors | RPS | mean | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 1 | 228 | 0 | **28.5** | 35.0 | 34.6 | **46.4** | 68.0 | 257.9 |
| 4 | 750 | 0 | **93.0** | 42.8 | 36.5 | **83.3** | 162.6 | 687.6 |
| 16 | 1255 | 0 | **150.7** | 103.1 | 41.2 | **258.5** | 1849.2 | 5105.2 |
| 64 | 1320 | 0 | **134.0** | 416.0 | 51.3 | **3001.1** | 5518.2 | 5808.5 |

- Peak throughput observed: **150.7 req/s** at concurrency 16, p95 **258.5 ms**.
- These are the only numbers that let you write the word *scale* on a resume. Whatever they are, they are yours and you can defend them.

> `predict` is a sync `def`, so Starlette runs it in a threadpool; the model is `n_jobs=1`, and a one-row DataFrame is constructed per call. If RPS stops rising while p95 climbs, you have found the saturation point — that is the sentence worth having, not a round number you guessed.

## Prediction log evidence

- SQLite path: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\runtime\serving-audit-workers-4.sqlite3`
- Successful prediction responses in this audit: **3557**
- New SQLite records captured in this audit: **3531**
- Record count did not match successful responses; investigate before treating this as an audit trail.

## Server stderr evidence

- Server stderr path: `C:\Users\adars\Desktop\One ML\student-mental-health-data-analysis\runtime\serving-audit-workers-4.stderr.log`
- Prediction-log write failures recorded by the server: **26**
- Stderr is written to a file instead of an unread subprocess pipe so error output cannot block worker processes during the load test.

## Ops surface

| artifact | present | notes |
|---|---|---|
| Dockerfile | yes | code-only image can be built and tested in CI |
| docker-compose.yml | **no** | no local multi-service stack |
| .dockerignore | yes | build context excludes raw data and artifacts |
| CI workflow | yes | tests and image build run on push and pull requests |
| Makefile / task runner | yes | documents host training, test, and container serving |
| /metrics endpoint | **no** | no Prometheus scrape target |
| structured request logging | **no** | a 500 leaves no trace — see the bare `except Exception` handler in api/main.py, which returns 500 without logging |
| prediction log / audit trail | yes | local SQLite records successful predictions |
| drift monitoring | **no** | nothing to compare against a baseline |
| load test in repo | yes | closed-loop request measurements are reproducible |
