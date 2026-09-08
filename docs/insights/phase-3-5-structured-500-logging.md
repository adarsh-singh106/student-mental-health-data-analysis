# Phase 3.5: Correlated Structured 500 Logging

## Status And Scope

This document records Close-out Plan task 3.5. The API already returned a generic
500 response when an unexpected exception escaped prediction. That was appropriate
for clients because it did not expose internal error text. It was inadequate for an
operator because the handler returned no useful event record.

This task adds:

- a generated request ID returned as the X-Request-ID response header;
- one JSON event for each unhandled request exception;
- method, path, HTTP status, exception type, and traceback in that event;
- a real Uvicorn audit that triggers an actual endpoint 500 and correlates it to
  server stderr.

It does not add alerting, distributed tracing, application-performance metrics, or
a complete incident-management system.

The question was:

> When a valid request reaches the model layer and fails unexpectedly, can an
> operator find the exact server-side event without giving the client a traceback
> or other internal implementation detail?

The answer is yes for the verified failure path exercised here.

## 1. What Was Wrong Before This Change

The prior exception handler did this:

    unexpected endpoint exception
        -> HTTP 500
        -> {"detail": "Internal server error"}
        -> no application error event

The client response was intentionally generic, but that left no useful answer to
basic operational questions:

| Question after a caller reports a 500 | Previous answer |
|---|---|
| Which request did the caller receive? | No correlation ID |
| What endpoint and method failed? | Unknown unless the caller supplied it separately |
| What exception type occurred? | Unknown |
| Was there a traceback? | Not from this handler |
| Can a support engineer connect the browser/API response to a server log? | No |
| Did the model fail after readiness succeeded? | Not reliably observable |

A generic 500 protects users. Silence protects no one. An operator needs the
internal event while the caller needs only a stable, non-sensitive failure contract.

## 2. Design Principles

### Separate Client Safety From Operator Detail

The service now has two intentionally different outputs for the same exception:

    client:
      HTTP 500
      {"detail": "Internal server error"}
      X-Request-ID: generated value

    operator stderr:
      one JSON object with request_id, method, path, status_code,
      exception_type, and traceback

The traceback never enters the JSON response. This matters because exception
messages, frame paths, dependency versions, or accidental data values can aid an
attacker or expose sensitive implementation detail.

### Correlation Needs An ID At The Boundary

The middleware creates a UUID4 hexadecimal request ID at the beginning of each
normal request lifecycle, stores it in request state, and places it in the response
header after the endpoint/exception handler produces a response.

The server generates the ID rather than trusting an incoming client-supplied header.
That keeps this first version simple and avoids allowing a caller to inject or
collide with an operator correlation ID. A future distributed system can validate
and propagate an upstream trace context, but it needs trust boundaries and a clear
sampling policy first.

The exception handler also has a fallback generator. If an error occurs before the
normal middleware state is present, the operator still gets an ID and the 500
response still carries it.

### Structured Means One Machine-Readable Event

The dedicated mental_health.api.events logger writes one JSON object per event to
stderr. The formatter includes:

| Field | Why it exists |
|---|---|
| timestamp | Orders and anchors the incident in time using UTC |
| level | Lets log storage/alerting distinguish errors from normal events |
| logger | Identifies the producer module |
| event | Stable semantic event name: unhandled_exception |
| request_id | Correlates the caller response with the server record |
| method and path | Identifies the failed API operation |
| status_code | Records the client-visible result |
| exception_type | Separates model/runtime failure classes without parsing free text |
| traceback | Preserves the exception context needed to debug it |
| message | A fixed human-readable event message |

JSON does not magically make logs observable. It makes fields queryable by an
event collector later. This project currently retains the stream only where the
process/platform sends stderr; it has no log shipper, retention policy, or alert.

## 3. Implementation

### Middleware And Handler

The request-ID middleware is in
[main.py](../../src/mental_health/api/main.py). It adds the header to normal 200,
422, 503, and handled 500 responses that traverse the application stack.

The unhandled-exception handler now:

1. retrieves the generated request ID from request state, or makes one if needed;
2. calls the structured event logger with method, path, and the actual exception;
3. returns the same generic 500 JSON body as before;
4. explicitly includes the request ID header on that fallback response.

The public response model for successful predictions was not changed. The new header
is additive HTTP metadata, not a new body field.

### JSON Formatter

[structured_logging.py](../../src/mental_health/api/structured_logging.py) owns the
event schema and the dedicated stderr handler. The handler is installed idempotently
so a development reload does not add one handler for every import. Its logger does
not propagate to the root logger, which prevents duplicate plain-text plus JSON
records for the same failure.

The traceback is formatted before logging and embedded as a JSON string. Newlines
are escaped inside the one JSON line, so a line-oriented log collector can parse a
single event without reassembling a multi-line Python traceback.

### Configurable Primary Artifact Root

The real audit needs a failing artifact without editing the shipped primary artifact.
For that purpose, artifact loading now resolves ARTIFACTS_ROOT when it is present,
otherwise it uses the same default artifacts directory as before.

This is a legitimate deployment configuration seam, not an error injection switch.
A container or server can mount a verified artifact at another read-only path. The
existing Docker path remains unchanged because it uses the default root. Unit tests
cover the override and existing code that calls load_latest_artifact without an
argument keeps working.

### Real Failure Artifact

The audit does not add a production environment flag such as FORCE_ERROR. That
would be a dangerous test-only behavior hidden in the API.

Instead, [audit_error_logging.py](../../audit/audit_error_logging.py) creates a
temporary artifact whose model object is an audit-only CrashingPipeline. The artifact
contains a model file, metadata, manifest, checksums, compatible pandas/sklearn
versions, and the current feature schema version. It therefore passes the ordinary
artifact verifier and reaches ready state.

Only when the real endpoint invokes its predict method does the fixture raise:

    RuntimeError: intentional error-audit failure

This matters because it tests a realistic class of incident:

    artifact loads successfully
        -> readiness returns 200
        -> inference code fails on a request
        -> caller receives generic 500
        -> operator gets correlated failure evidence

It also proves that readiness means the artifact was loaded and verified, not that
every possible inference call will succeed.

## 4. Options Considered

| Option | Benefit | Why it was not selected alone |
|---|---|---|
| Return exception text/traceback to caller | Easy immediate debugging | Leaks internals and makes the public contract unstable and unsafe. |
| Keep generic 500 with no log | Minimal code | An operator cannot investigate a real incident. This was the previous state. |
| Plain logger.exception output | Includes traceback | Free text is harder to query/correlate and can be split into several lines. |
| JSON error event, selected | Stable fields plus full debugging trace in one event | Needs a log destination, retention, and alerting before it becomes an operational system. |
| Accept X-Request-ID from the caller | Could join upstream traces | Requires input validation/trust policy. This project generates local IDs first. |
| Full OpenTelemetry tracing | Cross-service spans and sampling | Valuable with multiple services; unnecessary machinery for one local process and one error event. |
| Hosted error tracker | Deduplication, search, alerts | Requires credentials, network setup, privacy review, and vendor configuration. |
| Unit-test-only fake pipeline | Fast and isolated | Does not prove Uvicorn stderr formatting, HTTP headers, artifact loading, or real handler behavior. |
| Force-error environment flag | Easy live test | Adds a test backdoor to the application. The temporary verified artifact is safer. |

The choice follows first principles: do not expose internal errors to the client; do
record enough structured context for the operator; test the real request path rather
than only an isolated function.

## 5. Evidence From The Real Server

The reproducible command is:

    uv run --frozen python audit\audit_error_logging.py

The audit creates a temporary artifact outside the repository, starts one real local
Uvicorn process with ARTIFACTS_ROOT pointing at that artifact, waits for GET /readyz,
then sends a valid POST /predict request.

Result on 2026-09-08:

| Check | Result |
|---|---|
| Temporary artifact passed verification and /readyz | Yes, HTTP 200 |
| POST /predict status | 500 |
| Client body stayed generic | Yes: {"detail": "Internal server error"} |
| X-Request-ID present | Yes |
| JSON events parsed from server stderr | 1 |
| unhandled_exception events | 1 |
| Event request ID matched response header | Yes |
| Event exception type | RuntimeError |
| Event contained a traceback | Yes |
| Original exception text leaked to response | No |

The generated report is
[REPORT_error_logging.md](../../audit/REPORT_error_logging.md). It intentionally
does not copy the traceback into the tracked report. The full trace remains only in
the ignored runtime stderr log, because traces can contain details inappropriate for
source control.

The audit also checks the response body, request ID, event name, method, path,
status code, exception type, and trace content. It exits nonzero if any correlation
or disclosure assertion fails.

## 6. Failure Behavior And Boundaries

| Scenario | Current behavior | Is it sufficient? |
|---|---|---|
| A model predict call raises | Generic 500 response, request ID, JSON stderr event with trace | Good starting incident record. |
| Artifact fails verification/load | Existing readiness logic returns 503; this handler is not involved | Correct distinction between startup unavailable and request failure. |
| Client sends invalid input | FastAPI returns 422; no unhandled exception event | Correct: client validation failure is not a server exception. It is not yet an access/audit event. |
| Prediction-log SQLite write fails | Existing logger records the failure; valid prediction remains 200 | Separate Phase 3.1 availability trade-off. It is not yet a structured event. |
| Shadow candidate fails | Primary response remains available; current candidate exception uses normal application logging | The event can be upgraded to this schema later if candidate failures become operationally important. |
| JSON event handler/log destination fails | The client still should receive a generic 500, but operator visibility can be lost | No secondary durable log path, alert, or health signal exists. |
| Process/container restarts | Stderr history depends on the host/platform collector | No persistent central log storage exists. |
| Request fails before middleware state | Handler generates a fallback request ID | Better than no correlation, but exact full-lifecycle context may be limited. |

The behavior is intentionally narrower than "observability." An error log is a
necessary primitive, not a dashboard, SLO, pager, trace system, or incident response
process.

## 7. Security And Privacy Trade-offs

Logging a traceback is valuable and risky.

- The client never gets the traceback or the exception message.
- The JSON event does not intentionally include the request body.
- A traceback can still contain sensitive values if future code raises exceptions
  containing user input or secrets.
- Stderr access must be limited in any shared/public deployment.
- Logs need retention, deletion, encryption, and redaction decisions before real
  personal data is accepted.
- The existing prediction log already stores raw demographic/behavioral input, so
  the system is educational-only until those policies exist.

The generated request ID is an opaque random identifier, not a user ID, session ID,
authentication token, or idempotency key.

## 8. How Existing Behavior Was Protected

1. The successful prediction JSON response remains unchanged.
2. Existing generic 500 text remains unchanged; no internal exception is added to
   the response.
3. Existing default artifact loading remains unchanged when ARTIFACTS_ROOT is not
   set.
4. Shadow artifact loading continues to use an explicitly supplied separate root and
   does not depend on the new primary override.
5. The error fixture lives in audit code and the temporary artifact is deleted after
   the audit. No crashing model is published to artifacts/ or runtime/shadow-artifacts/.
6. Unit tests assert normal request IDs, generic 500 behavior, response header
   presence, event JSON fields, exception type, matching correlation ID, and trace
   presence.
7. The real Uvicorn audit verifies the behavior outside TestClient and then shuts
   down its local process tree.

## 9. Known Holes And Trigger Conditions

| Gap | Consequence | What would trigger a different design |
|---|---|---|
| No centralized log collection | Restarted container/host may lose the event | Public deployment, multiple replicas, or any operational incident response. |
| No alerting or SLO | An event can exist unnoticed | A user-impact or latency/error-rate objective. |
| No metrics for error rate | One can inspect individual events but not detect trend/volume | Sustained traffic or a reliability target. |
| No distributed trace propagation | IDs stop at this service boundary | Multiple services, queues, databases, or upstream gateways. |
| No structured events for 422, 503, logging failures, or candidate failures | The unhandled 500 path is better than the rest | Those paths become relevant to support/operations. |
| Raw traceback can contain sensitive details | Logging can create a data exposure | Real users, secrets, regulated data, or shared log access. |
| No log sampling/deduplication | Repeated faults can flood stderr | High-volume recurring failure. |
| No authenticated request identity | Request ID cannot identify a user/workflow safely | Public API or multi-tenant use. |
| No runbook | The next person still needs to decide what to do with an event | Team ownership and on-call expectations. |

## 10. Defensible Interview Explanation

A truthful description is:

> I kept the client-facing 500 generic but added a generated request ID and a
> dedicated JSON stderr event for unhandled API exceptions. The event includes method,
> path, status, exception type, and a traceback, and the response header carries the
> same ID. I tested it with a temporary artifact that passed the normal manifest,
> runtime compatibility, and schema checks, then raised only during predict. In a
> real Uvicorn run, readiness returned 200, the prediction returned a generic 500,
> and one JSON error event had the matching request ID and RuntimeError traceback.
> I would not call that full observability because there is no central collector,
> metrics, alerts, trace propagation, or privacy policy for logs.

Claims to avoid:

- "Built production observability."
- "Implemented distributed tracing."
- "Guaranteed no errors are lost."
- "Added a complete monitoring and alerting platform."
- "Made readiness prove model inference health."

None is supported by this implementation.

## 11. Position In The Close-out Plan

Task 3.5 is complete within its stated scope. The API now provides a stable client
failure response and an operator-visible correlated error record, with both unit and
real-server evidence.

All five Phase 3 request-path experiments now exist. Their combined lesson is not
that this small API is a finished platform. It is that each production practice was
introduced because a concrete request-path failure made its absence visible:

    persist successful requests
        -> discover shared SQLite contention under worker scaling
        -> stop malformed training CSVs at clear boundaries
        -> compare a candidate without serving it
        -> make real 500 failures findable

