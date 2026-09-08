# Phase 3.2: Worker Scaling

## Status And Scope

This document records Close-out Plan task 3.2: run the existing request-path
audit with four and eight Uvicorn worker processes, measure the result, and explain
what changed and what did not.

It is not evidence that this API is ready for an arbitrary number of users. It is a
single-machine experiment on one model release, one local dataset-derived request,
and one machine state. Its purpose is to make process-level concurrency, saturation,
and stateful side effects concrete.

The question was:

> Does adding Uvicorn worker processes improve the amount of real prediction work
> this service can complete, and what happens to latency and prediction logging as
> concurrency rises?

## 1. What Existed Before This Experiment

The API already had one useful load harness in
[audit_serving.py](../../audit/audit_serving.py). It starts the real FastAPI
application on a spare local port, waits for `/readyz`, sends validation probes, and
then runs closed-loop load at concurrency 1, 4, 16, and 64. "Closed loop" means a
client issues its next request only after its previous request completes. That is
appropriate for finding the service saturation point, but it is not a simulation of
an unbounded external traffic queue.

Before this task, the harness always started Uvicorn with its default one worker. It
could show that the request path slowed down as concurrency increased, but it could
not answer whether multiple application processes helped. It also used a subprocess
stderr pipe that no process drained. Under log-write failures, enough stderr output
could fill that pipe and block a worker. That made the early multi-worker results
unsafe to use.

The Phase 3.1 addition also changed the service boundary in an important way:

```text
request -> API validation -> sklearn prediction -> synchronous SQLite INSERT -> response
```

That final INSERT is local, durable, and deliberately best-effort. It is also a
shared write resource. Scaling inference processes does not make SQLite accept more
than one writer at a time.

## 2. The Principle Being Tested

### Worker Processes Are Local Horizontal Scaling

One Uvicorn worker is one Python process with one loaded model artifact. Asking
Uvicorn for four or eight workers creates several independent processes on the same
host. They can execute requests in parallel across CPU cores, and each has its own
Python interpreter, threadpool, model object, and memory allocation.

This is a small version of horizontal scaling:

```text
client load
    -> one Uvicorn supervisor
        -> worker 1: model loaded in memory
        -> worker 2: model loaded in memory
        -> worker 3: model loaded in memory
        -> worker 4: model loaded in memory
```

It is not the same as Kubernetes replicas or a cloud load balancer. All workers are
still on one laptop, share CPU, RAM, disk, and one SQLite file, and fail together if
the host fails. The only new question it answers is whether several local processes
serve this particular CPU-bound request path better than one.

### Why More Workers Might Help

`POST /predict` is a synchronous FastAPI endpoint. Starlette runs synchronous route
work in a threadpool inside each worker process. The sklearn `RandomForestRegressor`
in the released pipeline was trained/configured with `n_jobs=1`, so one prediction
does not itself fan out across all cores. Several Uvicorn processes can therefore
give the operating system more independent units of work to schedule.

### Why More Workers Might Hurt

Adding workers is not free:

| Cost | Why it matters here |
|---|---|
| Model copies | Each worker loads its own joblib artifact, increasing cold-start time and memory use. |
| CPU contention | More runnable Python processes than useful CPU work creates scheduling overhead rather than throughput. |
| Shared SQLite writer | Every successful request competes to insert into the same database. WAL helps readers, not multiple simultaneous writers. |
| Tail latency | A request can wait behind CPU work, threadpool work, or a database lock even when the median request remains quick. |
| Operational complexity | More processes need clean startup, readiness, shutdown, logs, and monitoring. |

The sensible question is therefore not "how many workers can I configure?" It is
"at what request rate and latency target does another worker produce measurable
benefit, and what shared dependency becomes the next bottleneck?"

## 3. Design Choices

### Options Considered

| Option | What it would show | Why it was not selected as the primary experiment |
|---|---|---|
| Change the model algorithm | Could change prediction cost | It would confound serving-process concurrency with model behavior. |
| Set sklearn `n_jobs=-1` | Uses more cores inside each request | It risks nested parallelism when several server workers run at once. The worker experiment needs the model kept at `n_jobs=1`. |
| Add a reverse proxy or Kubernetes | Introduces routing across replicas | That would add deployment infrastructure before proving that a second local process is useful. |
| Add Redis, Kafka, or PostgreSQL first | Could remove SQLite contention | It would hide the shared-state bottleneck instead of measuring it. The point is to experience the failure boundary of the current design. |
| Uvicorn `--workers 4`, then `--workers 8`, selected | Changes one serving dimension while leaving the model, endpoint, requests, and SQLite log in place | It is the smallest controlled change that tests process-level parallelism on this host. |

Four and eight workers were chosen as useful steps on a machine reporting 16 logical
CPUs. They are not a capacity recommendation. A different model, CPU topology,
memory limit, container CPU quota, or request mix can produce a different optimum.

### Harness Changes

[audit_serving.py](../../audit/audit_serving.py) now accepts:

```powershell
.venv\Scripts\python.exe audit\audit_serving.py --workers 4
.venv\Scripts\python.exe audit\audit_serving.py --workers 8
```

It gives each worker count its own SQLite path, server stderr file, and markdown
report. That prevents one run's records from being mistaken for another's:

```text
runtime/serving-audit-workers-4.sqlite3
runtime/serving-audit-workers-8.sqlite3
audit/REPORT_serving-workers-4.md
audit/REPORT_serving-workers-8.md
```

The harness now writes server stderr to a file rather than an unread pipe. The
change matters because Python subprocess pipes have finite buffers. When the API
logged repeated `database is locked` tracebacks during load, an unread pipe could
fill and block the process trying to write its error output. That is a harness
artifact, not the service behavior being measured.

On Windows, `proc.terminate()` stopped only Uvicorn's supervisor and could leave
spawned workers alive. The harness now calls `taskkill /PID <supervisor> /T /F` to
terminate the supervisor's process tree, then waits for it. A two-worker smoke test
verified that no local Python worker or listening audit port remained afterwards.
This is intentionally local-tooling code, not application production code.

## 4. Measurement Method

The final measurements were collected on 2026-09-08 against release
`20260908T061824666806Z-4888d94c`.

For each worker count, the harness:

1. Started the real API on a newly allocated localhost port.
2. Waited for `/readyz` to return 200, which confirms the artifact loaded.
3. Sent the existing valid and invalid API probes.
4. Ran eight seconds of closed-loop POST requests at concurrency 1, 4, 16, and 64.
5. Counted successful HTTP responses.
6. Counted new SQLite prediction records after the run.
7. Counted server messages reporting failed prediction-log writes.
8. Shut down the full Uvicorn process tree and verified no audit workers remained.

The harness uses the same validated payload for the load portion. It measures the
server and model path, not request diversity, authentication, network latency, or a
real user population.

## 5. Results

### Four Workers

| Concurrency | Requests | HTTP errors | Throughput | p95 latency |
|---:|---:|---:|---:|---:|
| 1 | 228 | 0 | 28.5 req/s | 46.4 ms |
| 4 | 750 | 0 | 93.0 req/s | 83.3 ms |
| 16 | 1,255 | 0 | **150.7 req/s** | **258.5 ms** |
| 64 | 1,320 | 0 | 134.0 req/s | 3,001.1 ms |

The four-worker run returned 3,557 successful prediction responses and inserted
3,531 new SQLite rows. The difference is exactly 26, and server stderr recorded 26
`database is locked` prediction-log failures.

### Eight Workers

| Concurrency | Requests | HTTP errors | Throughput | p95 latency |
|---:|---:|---:|---:|---:|
| 1 | 222 | 0 | 27.7 req/s | 49.5 ms |
| 4 | 732 | 0 | 89.8 req/s | 84.1 ms |
| 16 | 1,440 | 0 | **166.8 req/s** | **273.6 ms** |
| 64 | 1,553 | 0 | 134.4 req/s | 2,983.8 ms |

The eight-worker run returned 3,951 successful prediction responses and inserted
3,931 new SQLite rows. The difference is exactly 20, and server stderr recorded 20
`database is locked` prediction-log failures.

The raw generated reports are:

- [Four-worker serving audit](../../audit/REPORT_serving-workers-4.md)
- [Eight-worker serving audit](../../audit/REPORT_serving-workers-8.md)

They are historical Phase 3.2 snapshots. Their operations table correctly says
structured 500 logging was absent when these measurements were collected; Phase 3.5
adds that feature later in this branch. The throughput and SQLite-contestion numbers
remain the measured result of this worker-scaling configuration.

### Comparison

| Measure | 4 workers | 8 workers | Honest interpretation |
|---|---:|---:|---|
| Cold start to ready | 3.05 s | 3.85 s | More processes mean more artifact loads and startup work. |
| Peak observed throughput | 150.7 req/s | 166.8 req/s | Eight workers improved this run by about 10.7%, not by 2x. |
| Peak p95 latency | 258.5 ms | 273.6 ms | The added throughput came with a small worse p95 in this run. |
| Throughput at concurrency 64 | 134.0 req/s | 134.4 req/s | No meaningful high-concurrency gain is visible. |
| p95 at concurrency 64 | 3.00 s | 2.98 s | Both configurations are saturated for a latency-sensitive service. |
| Lost best-effort audit rows | 26 | 20 | Both configurations prove that SQLite logging is not a complete audit trail under this load. |

This is a single run per configuration. Differences of a few percent are normal
measurement noise. The defensible conclusion is not that eight is universally best.
It is that this host saw a modest peak-throughput improvement from four to eight
workers, while tail latency remained unacceptable at 64 concurrent clients and the
shared SQLite writer continued to lose best-effort audit records.

## 6. What The Numbers Mean

### Saturation And Queueing

At concurrency 16, both configurations reached their best observed throughput. At
concurrency 64, adding more in-flight callers did not add meaningful throughput but
pushed p95 near three seconds. That is the saturation signal:

```text
arrival pressure exceeds useful service capacity
    -> work waits for CPU, threadpool slots, or SQLite write access
    -> queues grow
    -> latency rises
    -> throughput stops improving
```

Little's Law offers a rough sanity check: with about 64 in-flight callers and about
134 req/s completed at the high-concurrency level, the average time in the system
should be on the order of 64 / 134 = 0.48 seconds. The observed means were 416 ms
and 385 ms. The exact values need not match because the closed-loop client does not
hold exactly 64 requests in every instant, but the direction is consistent: high
concurrency is being converted primarily into waiting time, not useful capacity.

The low median beside a multi-second p95 is also instructive. Some requests find an
idle worker and finish quickly. Others wait behind a burst of work or contend for
the database. Reporting only the mean or only the median would hide that user-facing
tail.

### Why HTTP Stayed Successful While Audit Rows Were Lost

Phase 3.1 deliberately chose fail-open logging: a successful model prediction still
returns 200 if `write_prediction()` catches an SQLite error. At four and eight
workers, that availability choice was exercised rather than assumed.

```text
prediction succeeds
    -> SQLite lock is available: commit one row, return 200
    -> SQLite remains locked past busy timeout: log error, return 200, audit gap
```

The equality between each response/row difference and stderr failure count is strong
evidence that the gap came from the designed fail-open error path. It does not make
the gap acceptable for systems that require a complete audit record. It proves why a
shared, single-writer local database is the wrong final sink when multiple workers
or replicas must record every request.

### What Has Not Been Measured

Do not extrapolate the result to "10,000 users" or a public cloud service. This
experiment did not measure:

- multiple hosts, containers, availability zones, or a load balancer;
- client network delay, TLS, authentication, rate limiting, or external services;
- memory consumption per loaded model worker;
- traffic with varied payload sizes or a production request mix;
- long-duration resource leaks, file growth, or restart recovery;
- a defined latency SLO or a traffic arrival process;
- dataset drift, prediction quality, labels, or model accuracy in production.

These omissions make the result narrow, not useless. The measurement is useful
because its boundary is named.

## 7. How Existing Behavior Was Protected

The experiment changes the audit harness, not the public model contract:

1. `PredictionRequest`, `PredictionResponse`, model artifact loading, preprocessing,
   and training code were not changed.
2. One-worker behavior remains the parser default, preserving the existing audit
   command and report destination.
3. Extra worker runs use separate logs and reports, so they do not overwrite the
   original single-worker evidence.
4. The server's stderr is captured to a per-run file. It is still available for
   investigation, but cannot become a hidden blocking pipe.
5. Process-tree cleanup is in `audit/`, where it belongs; it does not add Windows
   process-management behavior to the application image or API.
6. A two-worker real-service smoke run proved the cleanup path leaves no worker
   processes or listener behind.

## 8. Failure Scenarios Made Concrete

| Failure or pressure condition | What happened | Lesson |
|---|---|---|
| Single Uvicorn process cannot keep up | Request latency grows before the model changes | Serving capacity is an application concern, not only a model concern. |
| More workers share one SQLite file | `database is locked` errors occur during prediction logging | Stateless inference can scale, but stateful local side effects do not scale with it. |
| Fail-open logging meets contention | Client sees 200 but the audit record is absent | Availability and audit completeness are a deliberate trade-off, not a free guarantee. |
| Unread subprocess stderr fills | Earlier harness could block a worker on error output | Test tooling can create false performance incidents if it is not operated correctly. |
| Supervisor-only shutdown on Windows | Workers survived after the parent stopped | Processes need full lifecycle management; "it started" is not enough. |
| 64 concurrent callers hit saturation | p95 approaches three seconds with no throughput gain | Queueing and tail latency define capacity more honestly than a worker count. |

## 9. What A Different Architecture Would Require

Do not add infrastructure merely because the experiment found a limit. Add it when
the operating requirement demands it.

| New requirement | Design change | New responsibility it creates |
|---|---|---|
| Several workers must retain every audit event | Central database or a durable event stream with a consumer | Schema ownership, retries, idempotency, backup, access control, and alerting. |
| Several containers/hosts serve traffic | Stateless replicas behind a load balancer plus shared artifact and log destinations | Health checks, deployment rollout, replica capacity, network/security policy. |
| Logging must not affect response latency | Bounded asynchronous queue or batch writer | Backpressure, loss policy, consumer health, ordering, and durable acknowledgement semantics. |
| Tail latency must remain below a target | Define an SLO, load-test against it, cap concurrency or rate-limit callers | A visible overload policy and an alert when the limit is breached. |
| The model needs more compute | Measure CPU vs GPU batching only for a model/request shape that benefits | Device scheduling, batch-delay trade-offs, and utilization monitoring. |

For this repository today, the correct next step is not to install Kubernetes or
Kafka. It is to retain this measured limit, understand it, and continue exercising
the request path with schema breakage, shadow inference, and structured error logs.

## 10. Defensible Interview Explanation

A truthful description is:

> I parameterized a local FastAPI serving audit to run four and eight Uvicorn worker
> processes, isolated each run's SQLite audit log, and measured closed-loop
> throughput and p95 latency. Eight workers reached 166.8 req/s at 16 concurrent
> callers on my 16-logical-CPU machine, versus 150.7 req/s for four. At 64 callers,
> throughput stopped improving while p95 was about three seconds. The same test
> exposed SQLite write contention: the API stayed available by design, but 20 audit
> writes were lost at eight workers. I also fixed the benchmark's Windows shutdown
> path so worker processes could not contaminate later runs.

Claims to avoid:

- "Autoscaled a production service."
- "Built a horizontally scalable audit system."
- "Proved the service supports 10,000 users."
- "Implemented reliable multi-worker logging."

None follows from this local experiment.

## 11. Position In The Close-out Plan

Task 3.2 is complete within its stated scope. There are reproducible commands,
two real multi-worker reports, measured saturation, and an observed shared-state
failure. The next task is 3.3: deliberately break the training CSV contract and
record where each bad input stops. That experiment tests a different production
principle: fail loudly at the data boundary before invalid input reaches model
training or serving.
