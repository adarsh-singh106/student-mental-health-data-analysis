# Phase 3.4: Shadow-Run A Candidate Model

## Status And Scope

This document records Close-out Plan task 3.4: load the shipped model and a
min_samples_leaf=5 candidate together, return only the shipped model answer to the
caller, log both predictions, and compare them after 500 requests.

This is a local shadow-inference experiment. It is not evidence that a better model
was found, that a model was promoted automatically, or that the project now has a
production model registry and rollout controller.

The question was:

> Can a candidate artifact execute on the same validated requests as the released
> artifact, generate evidence about score differences, and fail without changing
> the caller-visible primary response?

The answer is yes for this service and the deliberately configured candidate. The
remaining limitations are explicit below.

## 1. The Problem Before This Change

Before this task, the API loaded exactly one artifact from the primary pointer:

    artifacts/latest.txt -> immutable artifact directory -> model.joblib

A new model could be evaluated offline, then manually published by replacing the
mutable latest pointer. That has an obvious gap: offline metrics do not tell an
operator how the candidate behaves on requests actually reaching the service.

The unsafe alternative would be:

    train candidate -> move production latest pointer -> discover behavior through users

That makes every caller part of the experiment. If the candidate has a preprocessing
bug, incompatible artifact, surprising output distribution, higher latency, or a
quality regression hidden by offline evaluation, the first evidence arrives after it
has affected users.

A shadow run gives a smaller and safer question:

    same validated request
        -> primary model: score returned to caller
        -> candidate model: score recorded only for later comparison

No caller receives the candidate score. A bad candidate is therefore observable
without becoming user-facing behavior.

## 2. Shadow, Canary, And Offline Evaluation Are Different

These terms are often used as interchangeable MLOps vocabulary. They are not.

| Method | Who receives candidate output? | What it can teach | Why it was or was not selected |
|---|---|---|---|
| Offline evaluation | Nobody | Performance on held-out historical data | Necessary release evidence, but cannot observe serving behavior on requests. Already exists. |
| Shadow inference, selected | Nobody | Candidate score, model-path cost, and errors on the same served inputs | Works with this project because requests can be generated and compared without risking a user response. |
| Canary release | A selected fraction of callers | User-facing latency/errors and, eventually, outcome differences | Requires real traffic and a decision about who gets an experimental result. This project has neither. |
| A/B experiment | Different user groups receive different variants | Causal product/outcome comparison | Needs real users, randomized assignment, and trustworthy outcome measurements. Not appropriate here. |
| Replace latest immediately | Every caller | Nothing before impact | This is a manual production cutover, not safe candidate evaluation. |

A shadow comparison also cannot establish which model is more accurate without
ground-truth labels that arrive later and can be joined to a request. It measures
disagreement, not correctness.

## 3. Candidate Selection And Provenance

The shipped primary artifact is:

| Property | Primary |
|---|---|
| Release ID | 20260908T061824666806Z-4888d94c |
| Artifact root | artifacts/ |
| Random forest min_samples_leaf | 1 |
| CV MAE mean | 0.338084 |
| CV MAE standard deviation | 0.008451 |
| Gate value: mean + standard deviation | 0.346535 |
| Training data SHA-256 | 32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3 |

The shadow candidate is:

| Property | Candidate |
|---|---|
| Release ID | 20260908T083535785394Z-ea390f9c |
| Artifact root | runtime/shadow-artifacts/ |
| Random forest min_samples_leaf | 5 |
| CV MAE mean | 0.383461 |
| CV MAE standard deviation | 0.010417 |
| Gate value: mean + standard deviation | 0.393878 |
| Gate threshold | Less than 0.400000 |
| Training data SHA-256 | 32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3 |
| Candidate Git provenance | Clean commit 546c0b0129082fc8fdc274897248ddba8292399f |

The candidate is deliberately not the offline winner. It passes the existing
eligibility gate, but its recorded CV MAE is worse than the primary. It was chosen
because a larger minimum leaf size is a clear, interpretable change: trees are less
able to create one-sample leaves and therefore produce smoother predictions. That
makes it useful for demonstrating a meaningful live comparison.

The primary and candidate metadata use different clean Git commits because the
candidate was built after Phase 3.1 serving work. The training and preprocessing
implementation at those commits was checked and is identical; the model-level
parameter difference is min_samples_leaf. The differing provenance is still
recorded rather than hidden.

The candidate was published into its own ignored root and has its own immutable
directory, manifest, checksum, environment metadata, and latest pointer. It cannot
modify the primary artifacts/latest.txt pointer.

A versioned future builder now exists at
[build_shadow_candidate.py](../../audit/build_shadow_candidate.py):

    uv run --frozen python audit\build_shadow_candidate.py --data-path "data/raw/Student Social Media And Mental Health Impact.csv"

It deliberately refuses to publish from a dirty Git tree, runs the same CV gate,
and writes only to runtime/shadow-artifacts/. The candidate used in this experiment
was generated from a clean checkout with the equivalent explicit configuration; the
script makes that workflow repeatable after this branch is committed and clean.

## 4. Selected Architecture

### Artifact Roots

    primary:
      artifacts/latest.txt
          -> 20260908T061824666806Z-4888d94c/
          -> verified primary pipeline

    optional candidate:
      runtime/shadow-artifacts/latest.txt
          -> 20260908T083535785394Z-ea390f9c/
          -> verified candidate pipeline

SHADOW_ARTIFACTS_ROOT is an operator-controlled environment variable. If it is
absent, the application behaves exactly as it did before: it loads and serves only
the primary artifact.

If it is present, the FastAPI lifespan handler loads the candidate through the same
load_latest_artifact verifier used for primary serving. The verifier checks the
pointer shape, artifact layout, manifest checksums, compatible pandas/sklearn
versions, and feature schema version before deserializing the pipeline.

The primary artifact is still the readiness dependency. A candidate load failure is
logged and leaves the shadow artifact state empty; GET /readyz can remain ready as
long as the primary is loadable. That is a deliberate availability decision. This
experiment treats the candidate as observational, not required for serving.

### Request Flow

    client
      -> FastAPI/Pydantic validates request
      -> primary pipeline predicts on a one-row DataFrame
      -> primary score and primary model-path latency are recorded in memory
      -> optional candidate predicts on a copy of that row
           -> candidate success: candidate score/version/latency recorded in memory
           -> candidate exception: log exception, keep primary result
      -> SQLite writes one row containing primary fields and optional candidate fields
      -> API returns only primary score and primary model version

The candidate executes after a successful primary prediction. That ordering ensures
a primary failure remains a normal primary failure, not a confusing candidate
incident. row.copy() prevents a future candidate pipeline that mutates its input
from changing the primary already-computed behavior.

The implementation is sequential, not parallel. It is intentionally easy to reason
about and lets one log row describe both scores. It also means the candidate adds
work to the request path, discussed under limitations. A higher-throughput
production shadow design might mirror requests to another service or use a bounded
asynchronous path, but that adds retry, backpressure, delivery, correlation, and
capacity problems that this experiment has not earned yet.

### Prediction-Log Extension

The existing SQLite predictions table gains three nullable fields:

| Column | Meaning |
|---|---|
| shadow_model_version | Immutable candidate artifact ID that produced the shadow score |
| shadow_output | Candidate numeric score for the same validated input |
| shadow_latency_ms | Candidate model-path latency from DataFrame copy through candidate prediction |

Primary fields remain unchanged. A row has either all three candidate fields or none.
write_prediction rejects partial candidate data rather than creating an ambiguous
comparison row.

Existing Phase 3.1 local databases are handled with a narrow additive migration:
initialize_prediction_log reads PRAGMA table_info(predictions) and adds only the
three known nullable columns when missing. This is not a general database migration
system. It is a targeted compatibility step for a local, internal table. Long-lived
or shared data stores need versioned migrations, rollback planning, and data
ownership beyond this code.

## 5. Why This Design Instead Of More Infrastructure

| Option | Benefit | Trade-off or reason not selected |
|---|---|---|
| Replace the primary pointer | Simplest operational action | Not a shadow experiment; every caller receives unproven behavior. |
| Return both scores in the API | Easy to inspect during testing | Leaks an unapproved candidate to consumers and creates a public contract that is hard to retract. |
| Run candidate on a percentage of requests only | Reduces extra compute | Sampling logic obscures this first experiment and can miss edge cases. All 500 controlled requests are clearer. |
| Send the candidate request to a second local API | Separates compute from primary response | Needs routing, request correlation, timeout policy, and separate process/container lifecycle. |
| Queue candidate work asynchronously | Protects primary request latency | Needs durable delivery, backlog limits, retry/idempotency, consumer monitoring, and a loss policy. |
| Load candidate from a separate artifact root, selected | Keeps immutable artifact verification and prevents primary-pointer movement | Requires an operator environment variable and duplicates model memory in one process. |
| SQLite nullable fields, selected | One query can compare the two scores for the same request | It inherits Phase 3.2 single-writer contention and is only a local comparison store. |
| Managed model registry | Stronger lifecycle, approvals, aliases, and access control | Useful in a team/platform setting, but would hide the artifact pointer and provenance principles already implemented here. |

The chosen design changes the minimum number of moving parts while making the
essential safety properties testable: separate identity, same input, primary-only
response, candidate failure isolation, and durable comparison evidence.

## 6. Evidence From 500 Real Service Requests

The reproducible audit is [audit_shadow.py](../../audit/audit_shadow.py):

    uv run --frozen python audit\audit_shadow.py

It starts a real Uvicorn process with the primary artifact and
SHADOW_ARTIFACTS_ROOT, sends 500 deterministic but varied valid request payloads,
then queries only SQLite rows created by that run. The payloads vary legal age,
gender, country, academic level, platform, purpose, use, unlock, study, activity,
sleep, and stress values. They are synthetic, not real users.

Result on 2026-09-08:

| Measurement | Result |
|---|---:|
| Primary HTTP responses | 500 |
| Public response contract failures | 0 |
| New prediction-log rows | 500 |
| Rows containing a candidate score | 500 |
| Candidate versions observed | 1: 20260908T083535785394Z-ea390f9c |
| Candidate prediction failures in stderr | 0 |
| Mean absolute primary-candidate score difference | 0.150538 |
| Maximum absolute primary-candidate score difference | 0.724448 |
| Mean logged primary model-path latency | 10.977 ms |
| Mean logged candidate model-path latency | 9.776 ms |

The raw result is in [REPORT_shadow.md](../../audit/REPORT_shadow.md).

The audit asserts all of the following:

1. Every HTTP response is 200.
2. Every response reports the primary release ID from /readyz.
3. No public response contains a field whose name starts with shadow_.
4. The number of new log rows matches successful responses.
5. The number of rows with candidate scores matches successful responses.
6. No candidate inference failure appears in server stderr.
7. The local Uvicorn process tree exits after the audit.

This is stronger evidence than a unit test alone because both joblib artifacts were
loaded by the running service and the comparison fields were queried from the real
SQLite database.

### How To Interpret The Difference

A mean absolute difference of 0.150538 does not say which model is better. A maximum
difference of 0.724448 is a useful investigation trigger: an operator could query
the logged input associated with the largest divergence and decide whether that
input is inside intended support, whether a feature interaction changed, or whether
the candidate needs more offline analysis.

To decide accuracy, the system would need future labels linked to each request,
enough samples, a pre-declared comparison metric, and a promotion policy. None
exists in this fixed CSV project, so promotion is intentionally not automated.

The logged latencies are model-path values only. They exclude HTTP transport,
Pydantic validation, SQLite insertion, and response serialization. The actual caller
waits for both sequential models plus the log write. These values should never be
presented as end-to-end API latency.

## 7. Failure Behavior

| Scenario | Current behavior | Is it sufficient? |
|---|---|---|
| Primary artifact cannot load | Service reports not ready; prediction returns 503 | Correct primary-serving behavior. |
| Candidate root is absent | No candidate is loaded; primary behavior is unchanged | Correct when shadow is intentionally disabled. |
| Candidate pointer/manifest/runtime schema is invalid | Candidate load is logged; primary remains ready and serves | Deliberate fail-open observation choice. The audit would fail because comparison rows are missing. |
| Candidate pipeline raises during prediction | Error is logged; primary 200 response remains available; candidate fields are null | Good isolation, but logging becomes properly structured only in Phase 3.5. |
| Primary pipeline raises | Existing generic 500 behavior applies; candidate is not attempted | Correct ordering. Phase 3.5 makes the error observable. |
| SQLite log write fails | Primary 200 response remains available; comparison can be lost | Deliberate Phase 3.1 trade-off, proven weak under multi-worker load in Phase 3.2. |
| Client retries a request | New duplicate comparison row can be created | No idempotency key exists. |
| Candidate score exists but labels never arrive | Difference is visible but quality is unknowable | Expected limitation of unlabeled shadow traffic. |

The API tests cover candidate load failure and candidate inference failure explicitly.
They prove a candidate cannot change the primary 200 response in those conditions.

## 8. How Existing Behavior Was Protected

The change was added around, not through, the primary contract.

1. PredictionRequest and PredictionResponse did not gain fields. Existing API
   clients see the same score, primary model version, and note as before.
2. The default remains no shadow root. Existing deployments do not load a second
   artifact unless an operator configures SHADOW_ARTIFACTS_ROOT.
3. The primary pointer and its immutable artifact directory are never written by
   candidate creation or serving code.
4. Both artifacts pass the same loader verification. The candidate is not trusted
   simply because an environment variable names its directory.
5. The default train behavior remains min_samples_leaf=1. A small build_pipeline
   seam exposes the candidate setting without changing the primary release
   configuration.
6. Candidate fields are nullable and additive in SQLite, so existing local Phase 3.1
   databases remain readable.
7. Tests cover default model construction, candidate construction, invalid leaf
   size, log migration, complete candidate rows, partial-row rejection, primary-only
   responses, candidate inference crash isolation, and candidate artifact load
   isolation.

## 9. Known Holes And Trigger Conditions

| Gap | Consequence | What would trigger a different design |
|---|---|---|
| Candidate executes sequentially in the primary request | It adds compute and can increase end-to-end caller latency | A latency SLO or sustained traffic makes shadow overhead unacceptable. |
| Every enabled request runs the candidate | CPU/memory use roughly grows with the second model | Higher traffic, expensive models, or a need to sample comparison traffic. |
| Candidate is in the same process | A pathological candidate can consume process memory/CPU even if its exception is caught | Stronger isolation or untrusted candidate code. |
| No real user traffic or delayed labels | The 500 synthetic requests measure disagreement, not production accuracy | A project with real events and trustworthy outcomes. |
| SQLite is the comparison store | Multi-worker writes can be lost, as Phase 3.2 measured | Multiple workers, replicas, audit requirements, or high volume. |
| Candidate load is fail-open | The service can silently lose comparisons unless logs/metrics are watched | Shadow completeness becomes a release requirement. |
| No promotion rule | Human judgment is required to swap the primary pointer | Repeated candidate releases with labels and accountable model ownership. |
| No request ID or structured error event yet | An individual divergence/candidate error is hard to trace across logs | Phase 3.5 begins this correlation work. |
| Artifact roots are local filesystem paths | They are not a shared registry across containers/hosts | Multi-replica or cloud deployment. |
| Raw inputs are logged | The existing privacy/retention risks remain | Any real user, sensitive data, or public deployment. |

## 10. What Production-Grade Shadowing Adds Later

Do not add all of this to a project with synthetic requests merely to look
enterprise-like. Understand the conditions that make each piece necessary.

| Requirement | Likely addition | New operational responsibility |
|---|---|---|
| Independent primary/candidate scaling | Separate model services behind a traffic mirror | Request correlation, network timeouts, service discovery, and capacity allocation. |
| Low caller latency | Asynchronous copy or bounded queue | Backpressure, queue durability, retries, lag monitoring, and loss semantics. |
| Partial shadow sampling | Deterministic sampling keyed by request ID | Sampling bias, sample-rate configuration, and statistical confidence. |
| Accurate winner selection | Delayed labels joined by request ID plus a pre-registered decision rule | Label quality, attribution, sample size, and approval governance. |
| Multi-host rollout | Model registry alias plus deployment controller | Auth, artifact access, rollback, approval, and audit trails. |
| Candidate error/SLO monitoring | Metrics, traces, alerts, and a runbook | Ownership and response expectations when alerts fire. |

## 11. Defensible Interview Explanation

A truthful description is:

> I added a local shadow-inference path for a gated RandomForest candidate with
> min_samples_leaf=5. The candidate uses a separate immutable artifact root and the
> same artifact verification as the primary. The endpoint always returns the primary
> score and version; it evaluates the candidate only for observation and stores
> candidate version, score, and model-path latency as nullable fields in the
> prediction audit row. I tested candidate load and inference failures to make sure
> the primary response stayed available. In a real 500-request Uvicorn audit, all
> 500 primary responses stayed unchanged and all 500 log rows contained both scores.
> Their mean absolute difference was 0.150538. I would not call that a model
> promotion result because the traffic was synthetic and no ground-truth labels
> exist.

Claims to avoid:

- "Implemented automated model promotion."
- "Proved the candidate was more accurate in production."
- "Built a production model registry."
- "Ran a canary release to real users."
- "Eliminated deployment risk."

None is supported by this implementation.

## 12. Position In The Close-out Plan

Task 3.4 is complete within its stated scope: separate candidate provenance,
same-input dual inference, primary-only response behavior, candidate failure
isolation, additive comparison logging, focused tests, and a 500-request running
service audit exist.

The final Phase 3 task is 3.5. The generic 500 handler currently hides internal
details from the caller correctly, but it emits no correlated structured record for
the operator. The next change adds request IDs, exception type, and traceback to
server logs, then deliberately triggers a real 500 to prove it can be found.

