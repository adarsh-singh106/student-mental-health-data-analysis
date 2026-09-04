# Serving audit

## Cold start

- process spawn -> `/readyz` 200: **2598 ms** (includes interpreter boot, sklearn import, and `joblib.load`)
- `/healthz` -> 200 in 11.0 ms
- `/readyz`  -> 200 in 22.3 ms  `{"status":"ready","model_version":"20260831T055753Z"}`

> The liveness/readiness split here is correct and worth saying out loud in an interview: `/healthz` answers *is the process up*, `/readyz` answers *can it serve*, and a missing artifact yields 503 rather than a crash loop. Most student projects have one `/health` that returns 200 unconditionally.

## Input validation behaviour

| probe | status | expectation | response (truncated) |
|---|---|---|---|
| valid baseline request | **200** | 200 with a score | `{"mental_health_score":7.649000000000002,"model_version":"20260831T055753Z","note":"Educational estimate only;` |
| unknown field added | **422** | 422 — extra='forbid' is set | `{"detail":[{"type":"extra_forbidden","loc":["body","Hacker"],"msg":"Extra inputs are not permitted","input":1}` |
| Age below range (12) | **422** | 422 — Field(ge=13) | `{"detail":[{"type":"greater_than_equal","loc":["body","Age"],"msg":"Input should be greater than or equal to 1` |
| Age as string '20' | **200** | pydantic v2 coerces -> 200 | `{"mental_health_score":7.649000000000002,"model_version":"20260831T055753Z","note":"Educational estimate only;` |
| Gender not in vocabulary | **422** | 422 — closed vocabulary. NOTE: this is a real user your API cannot serve. | `{"detail":[{"type":"value_error","loc":["body","Gender"],"msg":"Value error, Gender must be one of: Male, Fema` |
| unseen Country 'Wakanda' | **200** | 200 — OneHotEncoder(handle_unknown='infrequent_if_exist') absorbs it silently | `{"mental_health_score":7.660000000000002,"model_version":"20260831T055753Z","note":"Educational estimate only;` |
| time budget violated (sum>24) | **422** | 422 — cross-field model_validator | `{"detail":[{"type":"value_error","loc":["body"],"msg":"Value error, Avg_Daily_Usage_Hours + Study_Hours + Phys` |
| missing required field | **422** | 422 | `{"detail":[{"type":"missing","loc":["body","Sleep_Hours_Per_Night"],"msg":"Field required","input":{"Age":20,"` |
| null in a required field | **422** | 422 | `{"detail":[{"type":"float_type","loc":["body","Study_Hours"],"msg":"Input should be a valid number","input":nu` |
| negative usage hours | **422** | 422 — Field(ge=0) | `{"detail":[{"type":"greater_than_equal","loc":["body","Avg_Daily_Usage_Hours"],"msg":"Input should be greater ` |
| extreme-but-legal input | **200** | 200 — far outside training support, yet returned with no uncertainty signal | `{"mental_health_score":5.016,"model_version":"20260831T055753Z","note":"Educational estimate only; not a diagn` |

> Two rows deserve attention regardless of what they return. An unseen country is absorbed into an infrequent bucket and scored as if it were known — the caller is never told the input was out of vocabulary. And the extreme-but-legal row is scored with the same confidence as a typical one, because a point prediction carries no uncertainty. Neither is a crash; both are things you should be able to describe out loud.

## Latency and throughput

Closed-loop, 8s per level, single uvicorn worker, 16 logical CPUs on this machine. Latency in milliseconds.

| concurrency | requests | errors | RPS | mean | p50 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 1 | 442 | 0 | **55.2** | 18.0 | 16.0 | **32.4** | 36.8 | 45.6 |
| 4 | 740 | 0 | **92.5** | 43.2 | 41.7 | **58.4** | 67.9 | 110.4 |
| 16 | 742 | 0 | **91.5** | 174.0 | 170.2 | **214.3** | 254.9 | 278.4 |
| 64 | 753 | 0 | **87.3** | 708.6 | 725.8 | **804.5** | 816.0 | 825.2 |

- Peak throughput observed: **92.5 req/s** at concurrency 4, p95 **58.4 ms**.
- These are the only numbers that let you write the word *scale* on a resume. Whatever they are, they are yours and you can defend them.

> `predict` is a sync `def`, so Starlette runs it in a threadpool; the model is `n_jobs=1`, and a one-row DataFrame is constructed per call. If RPS stops rising while p95 climbs, you have found the saturation point — that is the sentence worth having, not a round number you guessed.

## Ops surface that does not exist in this repo

| artifact | present | consequence |
|---|---|---|
| Dockerfile | **no** | cannot run anywhere but your laptop |
| docker-compose.yml | **no** | no local multi-service stack |
| .dockerignore | **no** | n/a until a Dockerfile exists |
| CI workflow | yes | tests never run except by hand |
| Makefile / task runner | **no** | no single documented entrypoint |
| /metrics endpoint | **no** | no Prometheus scrape target |
| structured request logging | **no** | a 500 leaves no trace — see the bare `except Exception` handler in api/main.py, which returns 500 without logging |
| prediction log / audit trail | **no** | no record of what was served to whom |
| drift monitoring | **no** | nothing to compare against a baseline |
| load test in repo | **no** | the numbers above are not reproducible by a reader |
