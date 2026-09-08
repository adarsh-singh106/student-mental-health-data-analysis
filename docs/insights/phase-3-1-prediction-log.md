# Phase 3.1: Durable Prediction Logging

## Status And Scope

This document records the design, implementation, and measured result for Close-out
Plan task 3.1. It is deliberately a local request-audit experiment, not a claim that
this repository now has a complete production observability system.

The question was simple:

> After a successful prediction has been returned, can the system later show which
> validated input, model release, score, and model-path latency were served?

The answer is now yes for successful requests handled by this local service. The
answer is still no for malformed requests, model failures, lost disks, deleted
databases, and several other cases documented below.

## 1. The Problem Before This Change

### Previous Request Lifecycle

Before task 3.1, a valid request followed this path:

```text
client -> FastAPI validation -> pandas DataFrame -> sklearn pipeline.predict()
       -> JSON response -> process forgets the request
```

`POST /predict` returned a score and model version, but it wrote no durable record.
The process memory was the only place where the request ever existed. Restarting the
server, replacing the container, or simply waiting until after the response meant
the following information was gone.

| Question after a prediction | Previous answer | Why that is a problem |
|---|---|---|
| Which input produced this score? | Unknown | A surprising output cannot be investigated. |
| Which artifact version answered it? | Unknown after the response is lost | A release cannot be compared with what it actually served. |
| How many requests reached the model? | Unknown | There is no request-level evidence for later analysis. |
| What prediction latency did the model path take? | Unknown | A latency regression has no historical record. |
| Did a restart erase the request history? | Yes | No later audit is possible. |

This was acceptable for a single manual curl during development. It was not enough
to learn what it means to operate a model service. A model artifact has lineage from
training, but production also needs *serving lineage*: what was actually delivered
to callers by which release.

### What This Does Not Solve

Prediction logging does not prove model quality, catch drift, retrain a model, or
make the API scalable. This dataset does not receive real continuously changing
traffic, so adding those systems here would be theatre. The narrow useful outcome is
a durable record of moving requests.

## 2. Requirements And Non-Goals

### Requirements

The implementation needed to:

1. Persist one record for every successful model response.
2. Include the fields specified by the close-out plan: `id`, `timestamp`,
   `input_json`, `output`, `model_version`, and `latency_ms`.
3. Survive an application or container restart when the runtime directory is
   retained.
4. Avoid changing the public prediction response, model artifact, training code,
   validation rules, or release gate.
5. Be testable without a database server or a new runtime dependency.
6. Produce measured evidence, rather than only a source-code claim.

### Explicit Non-Goals

This task does not attempt to provide:

- A multi-host or high-throughput logging system.
- A dashboard, alert manager, or metrics backend.
- Request authentication, user identity, or tenant separation.
- Retention, deletion, encryption, consent, or privacy-policy enforcement.
- Exactly-once logging across client retries.
- Error-event logging for 422, 500, or 503 responses. Task 3.5 handles the
  unhandled-500 gap separately.
- A model-performance monitor. The log contains predictions, not future ground
  truth labels.

The omissions are design boundaries, not hidden claims of completeness.

## 3. Options Considered

The storage choice should follow the actual problem, not the list of tools commonly
shown in MLOps tutorials.

| Option | What it solves | Why it was not selected here, or its trade-off |
|---|---|---|
| Keep records in a Python list | Easy local debugging | Data disappears on restart, has no query interface, and grows unbounded in process memory. It fails the durable-audit requirement. |
| `print()` or normal server logs | Human-readable debugging | Container stdout can be discarded, logs are awkward to query by model version or time, and raw JSON lines do not provide transaction guarantees. |
| JSON Lines file | Simple append-only history | Concurrent writes, partial writes, filtering, indexing, and schema changes become application code. It is reasonable for a tiny single writer but weaker than SQLite for this experiment. |
| SQLite, selected | Durable local rows, SQL queries, transactions, no extra service | One writer at a time. It is suitable for this one-machine experiment, not a general horizontally scaled serving database. |
| PostgreSQL or managed relational database | Concurrent writers, backups, access controls, shared use by replicas | A real option once multiple processes or hosts need shared state. Adding and operating a database service before this project has real traffic would mostly teach deployment plumbing, not the request-path principle. |
| Redis | Fast transient event handling | Durability is configuration-dependent and it is not an audit database by default. It would add a separate service without solving the learning objective better than SQLite. |
| Queue plus consumer, such as RabbitMQ or Kafka | Decouples logging from response latency and can absorb bursts | Requires delivery semantics, consumer failure handling, idempotency, monitoring, and storage downstream. There is no sustained overload here to justify it yet. |
| Prometheus and Grafana | Aggregated request metrics and dashboards | They do not preserve one input-output record per prediction. A dashboard is not a substitute for an audit trail. |
| MLflow or another experiment tracker | Training and artifact lineage | Useful for experiments, but it does not answer which request a deployed model served. Training lineage and serving lineage are different concerns. |

### Why SQLite Was Chosen

SQLite meets the smallest set of requirements without inventing infrastructure:

- It is in the Python standard library, so `uv.lock` and the application dependency
  graph do not change.
- It writes a real on-disk database instead of keeping state in a process.
- SQL makes the audit result queryable by timestamp and model version.
- Transactions make each committed row atomic at the SQLite database level.
- It allows the project to measure the cost of making logging synchronous.

The choice is intentionally constrained. SQLite is not selected because it is the
best answer for a public multi-replica API. It is selected because the service is one
local process during this experiment and a full database platform would hide the
central lesson under unrelated setup work.

## 4. Selected Design

### Request Flow After The Change

```text
client
  -> FastAPI and Pydantic validate the HTTP body
  -> predict() creates a one-row DataFrame
  -> loaded sklearn pipeline produces a score
  -> application measures model-path latency
  -> SQLite INSERT commits one audit row
  -> existing JSON prediction response returns to the client
```

The logging call happens only after the pipeline has produced a score. Therefore a
422 validation failure, 503 artifact-unavailable response, or 500 model exception
does not create a prediction row. There was no successful prediction to audit in
those cases.

### Module Boundaries

| File | Responsibility | Why this boundary matters |
|---|---|---|
| [`prediction_log.py`](../../src/mental_health/api/prediction_log.py) | Resolves the database path, creates the table, and inserts a record. | SQLite concerns do not spread through API routing or model code. |
| [`main.py`](../../src/mental_health/api/main.py) | Initializes logging during lifespan and calls the logger after a successful prediction. | The endpoint remains the owner of request and response semantics. |
| [`audit_serving.py`](../../audit/audit_serving.py) | Starts the real service, sends requests, and compares response count with newly inserted rows. | Evidence is generated from the running process, not a mocked database. |
| [`test_prediction_log.py`](../../tests/unit/test_prediction_log.py) | Verifies row contents and a database-write failure. | Storage behavior is tested without FastAPI. |
| [`test_api.py`](../../tests/unit/test_api.py) | Verifies endpoint persistence and response availability when logging fails. | The public API contract remains protected. |

No training, preprocessing, artifact serialization, model schema, API request schema,
or response schema was modified for this task.

### Storage Contract

The `predictions` table is created idempotently with `CREATE TABLE IF NOT EXISTS`.
The current contract is:

| Column | Meaning | Important limitation |
|---|---|---|
| `id` | SQLite integer primary key, assigned on insert. | It is not a caller request ID and cannot deduplicate retries. |
| `timestamp` | UTC ISO-8601 time immediately before the insert. | It uses the host clock; it is not a distributed trace timestamp. |
| `input_json` | Canonical compact JSON of Pydantic-validated input, sorted by key. | It contains raw demographic and behavioral fields. |
| `output` | Numeric model score returned to the caller. | It is a prediction, not a future observed outcome. |
| `model_version` | Artifact release ID loaded by the server. | It identifies the release, not every runtime setting or hardware fact. |
| `latency_ms` | Time from DataFrame construction through `pipeline.predict()`. | It excludes HTTP network time, Pydantic validation, SQLite insertion, and response serialization. |

`json.dumps(..., allow_nan=False)` refuses non-finite values, and the payload has
already passed Pydantic validation. Key sorting makes equivalent validated payloads
serialize consistently, which improves later comparisons.

### Database Behavior

At application startup, the FastAPI lifespan handler attempts to create the parent
directory and database table. It enables SQLite write-ahead logging (WAL) and sets a
five-second busy timeout for each connection.

WAL is not a scalability switch. It generally lets readers coexist better with a
writer, but SQLite still permits only one writer at a time. Each successful request
opens a short-lived connection, inserts one row, commits when the connection context
exits normally, and closes it. That simple design is intentionally visible in the
load-test result.

The default database path is repository-root `runtime/predictions.sqlite3`.
`PREDICTION_LOG_PATH` overrides it, which lets tests use a temporary file and lets a
deployment choose another mounted directory. `make serve` binds host `runtime/` to
`/app/runtime` and sets the container path explicitly.

The tracked `runtime/.gitkeep` ensures a fresh clone has the bind-mount directory.
SQLite databases, WAL files, and shared-memory files remain ignored so raw request
records cannot accidentally be committed.

## 5. Failure Boundary And Availability Decision

The key design decision is that an audit write must not turn a valid model answer
into an API failure. The code therefore treats prediction logging as a best-effort
side effect of a successful response.

```text
model prediction succeeds
  -> SQLite write succeeds: return normal 200 and durable row
  -> SQLite write fails: log traceback, return normal 200, audit gap exists
```

This favors caller availability over perfect audit completeness. It is not a free
choice. A system with legal or financial audit requirements might instead fail the
request, enqueue a durably acknowledged event, or expose a degraded readiness state.
Those choices have different user-impact and operational consequences.

The current implementation catches expected storage and serialization failures:
`OSError`, `sqlite3.Error`, `TypeError`, and `ValueError`. It logs the exception and
returns `False` to the caller. The API does not expose that boolean to clients.

At startup, failure to initialize SQLite sets `app.state.prediction_log_path` to
`None`. The model can still be ready because `/readyz` intentionally answers whether
the model artifact can serve, not whether request auditing is available. This is a
conscious availability choice and also a known observability hole.

## 6. Failure Scenarios And Current Behavior

| Scenario | Current behavior | Is that sufficient? |
|---|---|---|
| Runtime directory does not exist | Startup creates it. | Yes for local use. |
| Database path is unavailable during startup | Server logs the exception, disables prediction persistence, and may still report model-ready. | Deliberate for availability, insufficient when audit completeness is mandatory. |
| Database becomes unavailable during a request | `write_prediction` logs a traceback and the client still receives the valid 200 response. | Useful fault isolation, but no alert or repair path exists. |
| Client sends invalid JSON or invalid fields | FastAPI returns 422 before endpoint inference; no prediction row exists. | Reasonable for this table, but rejected traffic is not auditable yet. |
| Artifact cannot load | `/predict` returns 503; no prediction row exists. | Correct for serving, but startup logs are not yet structured. |
| Pipeline raises after validation | Existing generic 500 response returns; no prediction row exists. | Incomplete. Phase 3.5 adds request ID, exception type, and traceback logging. |
| Process stops before the transaction commits | The last record can be absent. | Expected. SQLite cannot persist a transaction that never committed. |
| Host disk or mounted volume is lost | History is lost. | No backup, replication, or disaster recovery exists. |
| Many concurrent requests write at once | Writes serialize; callers can wait up to the busy timeout and throughput can fall. | This is the next experiment's pressure point, not solved preemptively. |
| Client retries the same request | Multiple rows can be written. | No idempotency key or deduplication exists. |

## 7. How Existing Behavior Was Protected

The implementation was intentionally added at a narrow boundary rather than woven
through the whole repository.

1. The prediction API still validates the same `PredictionRequest` and returns the
   same `PredictionResponse`. No field was added to or removed from the public HTTP
   contract.
2. The model receives the same columns as before. The payload dictionary is reused
   only to construct the DataFrame and then serialize the audit record.
3. Model loading, readiness semantics, release validation, preprocessing, and
   training remain separate from the new module.
4. Unit tests monkeypatch the database path to a temporary file. Tests cannot pollute
   the real local audit database or depend on its previous contents.
5. The database-specific test proves exact row contents. The endpoint test proves
   the returned score and model version remain correct after persistence is added.
6. A failure-isolation test proves a valid prediction remains a 200 when the logging
   function reports failure.
7. No third-party package was added. The lockfile and deployable dependency set stay
   unchanged.

This is not proof that every production integration is safe. It is evidence that the
change did not regress the repository's existing tested behavior.

## 8. Evidence Collected

### Automated Tests

The full suite was run after implementation:

```powershell
uv run --frozen pytest
```

Result: **29 passed**. The relevant new tests cover:

| Test | What it proves |
|---|---|
| `test_write_prediction_persists_the_served_record` | The table contains the expected ID, timezone-aware timestamp, JSON input, output, release version, and latency. |
| `test_write_prediction_returns_false_when_sqlite_is_unavailable` | A database error is caught and logged rather than escaping from the storage module. |
| `test_predict_persists_the_served_request` | A real FastAPI prediction stores the exact validated request, score, model version, and non-negative model-path latency. |
| `test_predict_remains_available_when_prediction_logging_fails` | A logging failure does not change a valid prediction from 200 to 500. |

### Real Serving Audit

Command run on 2026-09-08:

```powershell
.venv\Scripts\python.exe audit\audit_serving.py
```

The audit started the real release
`20260908T061824666806Z-4888d94c`, then sent validation probes and closed-loop load
for eight seconds at concurrency levels 1, 4, 16, and 64. Before starting the
server, the audit stored the latest SQLite row ID. After stopping the server, it
queried `COUNT(*) WHERE id > previous_id`. This isolates rows from the current run
without deleting prior audit history.

| Measurement | Result |
|---|---:|
| Successful model responses in this audit | 1,132 |
| New SQLite rows after this audit | 1,132 |
| Record-count match | Exact |
| Peak observed throughput | 36.0 req/s at concurrency 16 |
| p95 latency at that peak | 558.1 ms |
| Cold start to `/readyz` 200 | 2,574 ms |

The full generated evidence is in [the serving audit](../../audit/REPORT_serving.md).

### Performance Interpretation

The older no-log audit recorded 92.5 req/s at concurrency 4 with p95 58.4 ms. The
current audit peaked at 36.0 req/s with p95 558.1 ms. These are separate runs, so
they are not a controlled experiment proving that SQLite alone caused the change.
The model release and machine state can also affect performance.

They are still strong enough evidence for the only defensible conclusion: a
synchronous, one-connection-per-request SQLite write is visible on this request
path and must not be advertised as a high-throughput design. The external audit
latency includes the database work; stored `latency_ms` intentionally does not.

## 9. Known Gaps And Why They Matter

This implementation has real holes. Naming them is more useful than adding an
unjustified stack of tools.

| Gap | Consequence | What would trigger a different design |
|---|---|---|
| Raw request fields are stored | Age, gender, country, and behavioral values may be sensitive. | Any real public user or regulated data requires consent, minimization, access control, retention/deletion policy, and likely redaction. |
| No authentication or authorization | Anyone with filesystem access can read the database. | Shared host, cloud deployment, or real users. |
| No encryption | Database contents are plain local files. | Sensitive data at rest or in backup. |
| No retention or deletion job | The database grows forever. | Long-running service or data policy requirement. |
| No alert on write failure | The API can look healthy while audit rows disappear. | Audit completeness becomes operationally important. |
| `/readyz` ignores logging availability | Traffic can be routed to a model with no audit trail. | Logging becomes a hard serving dependency. |
| No rejected-request or error-event records | 422, 500, and 503 incidents are not represented in this table. | Need to investigate all caller-visible failures; Phase 3.5 begins this work for 500s. |
| No request ID or idempotency key | Retried requests can create duplicate rows and records cannot be tied to a caller trace. | Retries, downstream workflows, or support investigations become real. |
| SQLite is one-host, one-writer-oriented | More workers or replicas contend on writes; host-local files are not shared. | Multiple Uvicorn workers, container replicas, or more than one host. |
| Synchronous write on response path | Logging can increase client latency and reduce throughput. | Sustained traffic approaches the measured saturation point. |
| No backups or replication | Host or volume loss destroys history. | Audit data becomes valuable enough to preserve. |
| No schema migration strategy | Future table changes may require manual data handling. | The table becomes long-lived or externally consumed. |
| No labels or outcomes | The table cannot measure prediction accuracy after deployment. | Ground-truth outcomes arrive later with trustworthy joins. |

## 10. What Would Change In A More Demanding System

Do not add these components before their triggering conditions exist. The point is
to understand why the architecture would change.

| New condition | Likely design change | Reason |
|---|---|---|
| Four or eight worker processes show SQLite contention in Phase 3.2 | Measure first; then consider a central database or a bounded asynchronous event path. | Host-local SQLite does not coordinate a horizontally scaled service well. |
| Multiple containers or hosts serve requests | Central managed relational storage, or durable event ingestion plus a consumer. | All replicas need one shared, durable audit destination. |
| Logging must not add request latency | Queue or buffered batch writer with explicit delivery, backpressure, retry, and loss semantics. | Decoupling improves latency but creates a new reliability system to operate. |
| Logging must never be lost | Acknowledged durable event path, monitoring, alerting, and a clear decision about fail-open versus fail-closed serving. | The current best-effort behavior intentionally allows audit gaps. |
| Real users provide personal data | Privacy review, minimization, redaction, encryption, authorization, retention, and deletion controls. | Raw input capture becomes a data-governance problem. |
| Ground truth arrives later | Joinable request IDs, label ingestion, delayed-performance evaluation, and an approval/retraining policy. | Predictions alone cannot detect model-quality degradation. |

## 11. Defensible Interview Explanation

A truthful description is:

> I added local durable serving lineage to a FastAPI model service. Each successful
> prediction records the validated input, release ID, output, and model-path latency
> in SQLite. I used a failure-isolated write so a logging outage does not return a
> false 500 to the caller, then load-tested it and verified 1,132 successful responses
> produced 1,132 rows. The experiment also showed that synchronous SQLite writes hurt
> throughput, so I documented it as a local audit design rather than a scalable
> production logging system.

Claims to avoid:

- "Built production observability."
- "Implemented scalable monitoring."
- "Created exactly-once prediction logging."
- "Built a high-throughput audit pipeline."

Those claims are not supported by this implementation or its evidence.

## 12. Position In The Close-out Plan

Task 3.1 is complete when judged by its stated scope: a durable prediction log,
running-service measurement, SQLite query, and written result now exist.

The next task is 3.2, worker scaling. The current SQLite design must remain in that
experiment. It would be dishonest to replace it with a queue or a hosted database
before measuring what multiple Uvicorn worker processes actually do to latency,
throughput, and record completeness on this machine.
