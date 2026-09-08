# Phase 3.3: Deliberate Schema Breakage

## Status And Scope

This document records Close-out Plan task 3.3. The project already had a raw CSV
column contract and Pandera validation from earlier work. This task did not pretend
that a validator is proven merely because it exists. It broke three temporary CSV
copies and recorded the exact layer, exception class, and error detail that stopped
each one.

The source dataset was never modified.

The question was:

> If an upstream CSV changes shape or type, does the training preparation pipeline
> fail at a clear boundary before cleaning, sklearn transformation, or model fitting
> can make the incident harder to understand?

For the three tested failures, the answer is yes. It is not a claim that every
possible corrupt input is handled perfectly. The remaining gaps are named below.

## 1. Why This Experiment Matters

A model pipeline often fails long after an upstream data contract was broken:

```text
upstream export changes
    -> CSV loader accepts it
    -> cleaning changes or crashes on it
    -> sklearn receives a different frame
    -> training fails obscurely, or worse, produces a model with changed meaning
```

The useful property is not simply "there is validation." It is failure locality:
the first layer that understands the problem should reject it loudly, with an error
that tells an operator what changed.

Before this experiment, the repository contained two relevant layers:

```text
pd.read_csv
    -> validate_column_contract(raw_df)
    -> remove_duplicates()
    -> fix_physical_activity_hours()
    -> Pandera SocialMediaUsageSchema.validate(...)
    -> sklearn training pipeline
```

The explicit structural validator checks expected, unexpected, and duplicate column
names. It runs before cleaning because the cleaning function indexes
`Physical_Activity_Hours` by name. Pandera then validates values, allowed
categories, cross-column constraints, and declared types after the intentional
cleaning step.

The earlier implementation was reasonable, but unmeasured behavior is still an
assumption. This task converts the assumption into an executable experiment and
report.

## 2. The Data Contract Being Protected

The training CSV is expected to contain the 12 feature columns and
`Mental_Health_Score` target, with no extras or duplicates. The names come from
`EXPECTED_COLUMNS` in
[schema.py](../../src/mental_health/data/schema.py).

The contract has two different layers:

| Layer | What it validates | Why it is placed there |
|---|---|---|
| `validate_column_contract` | Missing, unexpected, and duplicate column names | It runs before cleaning can raise an accidental `KeyError`, and emits a domain-specific `DataContractError`. |
| `SocialMediaUsageSchema` (Pandera) | Types, ranges, category vocabulary, nullability, and the daily-time cross-field rule | It validates dataframe contents after the known negative activity-hour correction. |
| sklearn pipeline | Feature preprocessing and model inference | It should receive only a prepared dataframe. It is not the first-line raw-data contract. |

The distinction matters. A missing column is a structural schema drift problem. A
non-numeric value in an existing column is a semantic/type problem. Treating both as
one generic "training failed" event loses the useful diagnostic information.

## 3. Experiment Design

### Safety Boundary

The audit reads the real local CSV once, makes all mutations in a new
`TemporaryDirectory`, and passes each temporary file to `prepare_data()`. It never
writes to the raw input file. The source file therefore remains the known input used
by the current released artifact.

The reproducible command is:

```powershell
uv run --frozen python audit\audit_schema_failures.py
```

The script writes [REPORT_schema_failures.md](../../audit/REPORT_schema_failures.md).
It also checks the unmodified source as a control before running any mutation.

### Why These Three Mutations

| Case | Concrete mutation | Production analogue | Expected boundary |
|---|---|---|---|
| Unexpected column | Add `Audit_Unexpected_Column` | An upstream export adds a field or a different version of an extract is supplied | Structural column contract |
| Missing cleaning dependency | Delete `Physical_Activity_Hours` | A supplier renames/removes a required feature | Structural column contract before the cleaner indexes it |
| Non-numeric Age | Replace one value with `not-an-integer` | A bad value, spreadsheet edit, or upstream type regression corrupts a numeric field | Pandera type/value validation |

The non-numeric test deliberately uses a value that cannot be parsed as an integer.
A CSV value such as `"20"` is not a useful failure test: pandas/Pandera can
legitimately parse or coerce it to an integer. The question is whether a truly
invalid representation is rejected, not whether benign CSV string formatting is
forbidden.

## 4. Results

The experiment was run on 2026-09-08. The raw source was read as 5,000 rows and 13
columns. After existing duplicate removal and physical-activity correction,
`prepare_data()` accepted 4,998 rows and 13 columns as the control.

### Case 1: Unexpected Column

```text
Raw dataset column contract failed:
unexpected=['Audit_Unexpected_Column']
```

| Property | Result |
|---|---|
| Failure boundary | Structural column contract |
| Exception | `DataContractError` before cleaning |
| Cleaning executed | No |
| Pandera executed | No |
| sklearn reached | No |
| Failure clarity | High: the unexpected name is in the message |

This is the desired result. Without the early name check, one of several poorer
outcomes is possible: an extra field could be silently ignored, a strict schema
could reject it only after cleaning has done work, or a future cleaning function
could accidentally use it.

### Case 2: Missing `Physical_Activity_Hours`

```text
Raw dataset column contract failed:
missing=['Physical_Activity_Hours']
```

| Property | Result |
|---|---|
| Failure boundary | Structural column contract |
| Exception | `DataContractError` before cleaning |
| Cleaning executed | No |
| Pandera executed | No |
| sklearn reached | No |
| Failure clarity | High: the missing required feature is named |

This case is more valuable than removing an arbitrary unused field. The next
function, `fix_physical_activity_hours()`, reads
`df["Physical_Activity_Hours"]`. Without the structural check, it would raise a
generic pandas `KeyError`. That would reveal a symptom in cleaning but not tell the
operator that the raw data contract had changed. The current ordering correctly
turns it into an explicit upstream-contract failure.

### Case 3: Non-numeric Age

Pandera rejected one `Age` value, `not-an-integer`, with four lazy-validation
failure cases. The first two are the important ones:

```text
coerce_dtype('int64'): not-an-integer
dtype('int64'):        not-an-integer
```

The range checks also reported type-comparison errors because the bad string cannot
be compared to the integer range limits. Pandera's lazy mode collects all these
related failures instead of terminating at only the first one.

| Property | Result |
|---|---|
| Failure boundary | Pandera dataframe validation |
| Exception | `SchemaErrors` with four failure cases after cleaning |
| Structural contract passed | Yes, because the column name remained correct |
| Cleaning executed | Yes; it does not depend on `Age` |
| sklearn reached | No |
| Failure clarity | Good: the error includes column, failed coercion, value, and row index |

The generated audit captures a compact machine-readable rendering of the first
failure cases. The application logger also emitted Pandera's full failure-case table
during the run. That is noisier than a public API response should be, but appropriate
for a batch training preparation failure.

## 5. What Was Actually Proven

The exact result is:

```text
extra/missing names -> domain-specific DataContractError before cleaning
bad Age value        -> Pandera SchemaErrors after cleaning
all three cases      -> no sklearn transform, fit, or prediction
```

That is useful because a failed training job now points its operator toward the
upstream input contract instead of looking like a model bug.

It does not prove that the CSV is valid in a business sense, that the data is
representative, that the model is accurate, or that a production consumer will
receive good API responses. Schema validation protects format and defined invariants;
it does not make an undocumented, likely generated mental-health dataset suitable
for clinical use.

## 6. Why This Design Was Chosen

### Options Considered

| Option | Benefit | Limitation or reason not selected alone |
|---|---|---|
| Let pandas/sklearn fail naturally | No extra validation code | Errors occur late and can be vague, dependent on implementation details, or silent for unused columns. |
| Pandera only | Validates values and has `strict=True` | It runs after this repository's cleaner. A missing cleaning input can fail as a `KeyError` first. |
| Custom column contract only | Gives clear missing/extra/duplicate-name errors | It does not validate types, ranges, categories, or cross-column relationships. |
| Custom structural check plus Pandera, selected | Each layer handles the failure it understands | Two mechanisms need tests and documentation, but the ordering produces clearer incidents. |
| Pydantic request model | Strong API request validation | It protects JSON inference requests, not the batch CSV consumed during training. |
| Great Expectations or a data-quality platform | Rich profiling, suites, and reporting | Adds another framework without improving this narrow training boundary yet. The current invariant set is small and code-local. |
| Schema registry | Coordinates versioned producer/consumer contracts | Useful when independent upstream producers exist. This project has a local CSV, not an evolving distributed data interface. |

The selected design follows a first-principles rule: reject structural changes before
code indexes named fields; validate content before model code uses it; make each
failure specific enough to route to the owner of the broken contract.

### Why Pandera Coercion Remains Enabled

`SocialMediaUsageSchema.Config.coerce = True` permits data that is semantically
numeric but serialized as text to become the declared numeric dtype. CSV has no
native type system, so that tolerance is useful. Disabling coercion would reject
harmless exports such as a numeric column represented as strings.

Coercion is not blind acceptance. A value such as `not-an-integer` cannot be coerced
and fails. This is the right distinction for a CSV import boundary: normalize
equivalent representation, reject changed meaning.

## 7. How Existing Behavior Was Protected

No production validation or model behavior was loosened for this task.

1. The experiment only creates temporary CSV files; it does not edit the source
   dataset or publish an artifact.
2. The `prepare_data()` call is the same entrypoint used by training. The audit does
   not mock its validators or bypass cleaning.
3. Three focused integration tests now protect the observed boundaries:
   - missing `Physical_Activity_Hours` raises `DataContractError`;
   - an unexpected column raises `DataContractError`;
   - non-coercible `Age` raises Pandera `SchemaErrors`.
4. The tests use copies of the small preparation fixture in a pytest temporary
   directory. They do not rely on the local raw dataset, its undocumented source,
   or its file path.
5. Training, artifact serialization, release gates, API request validation, and
   public response contracts were not changed.

## 8. Real Holes That Still Exist

This task is intentionally not a claim of complete data quality.

| Gap | Consequence | What would change the design |
|---|---|---|
| Cleaning runs before full value/type validation | A non-numeric `Physical_Activity_Hours` can cause the cleaner's `< 0` comparison to raise a generic Python/pandas type error before Pandera gives a structured report. | If upstream data becomes a real operational input, add a pre-clean parse/type boundary or make cleaning defensive around malformed values. |
| No quarantine or rejected-file store | A failed CSV is reported but not retained with metadata for later investigation. | Recurring batch ingestion or a data-support workflow. |
| No producer-owned schema version in the CSV | The consumer cannot distinguish an intentional schema migration from accidental drift. | Independent producers or planned schema evolution. |
| No automated source checksum gate before training | A changed file is detected in artifact metadata after training, not necessarily blocked before it. | A release policy that allows only approved datasets. |
| No null/duplicate policy beyond present code | Some values are rejected, and duplicate rows are silently removed, but no operator approval is required. | Data quality becomes consequential enough that silent correction is unsafe. |
| No semantic distribution checks | Values can satisfy ranges/categories yet represent a changed population or generated data pattern. | Trusted time-series data and a defined reference distribution. |
| Batch validation logs are not yet structured incident events | The exception is visible locally but has no request/job correlation ID, alert, or dashboard. | Scheduled/remote training with operational ownership. |
| Data provenance is weak | A schema-valid file can still be legally, ethically, or scientifically unsuitable. | Any non-educational use or real human decisions. |

The first gap is important enough to say aloud in an interview. The experiment proves
the chosen `Age` failure reaches Pandera. It does not prove every bad dtype does.
That distinction is more credible than saying "Pandera catches all bad data."

## 9. Failure Scenarios And Ownership

| What breaks | Current behavior | First owner to investigate |
|---|---|---|
| Source adds a field | Training preparation raises `DataContractError` naming it | Upstream export/schema owner |
| Source removes/renames a feature | Training preparation raises `DataContractError` naming it | Upstream export/schema owner |
| Age contains a non-numeric value | Pandera logs/report lists row and coercion failure | Data producer or ingestion owner |
| Activity-hour value is non-numeric | May fail in cleaning before structured Pandera validation | Current code owner; this is a known improvement boundary |
| Values are valid-looking but shifted | Preparation accepts them | Requires a future data-quality/drift design, not this fixed CSV experiment |
| Schema is intentionally changed | Training fails until constants/schema, tests, artifact schema version, and release review are updated | Joint producer/ML owner change process |

The desired operational result is not that the service keeps training on every input.
For model training, a loud failure before artifact publication is usually safer than
a "best effort" repair that changes feature meaning invisibly.

## 10. Defensible Interview Explanation

A truthful description is:

> I tested the training data boundary by mutating temporary CSV copies rather than
> changing the source file. An unexpected field and a missing feature both raised a
> domain-specific structural-contract error before cleaning. A non-numeric Age
> passed the column-name check but Pandera rejected it after cleaning with four
> lazy-validation failure cases, before sklearn was reached. I then added regression
> tests for those three boundaries. I would not claim the validation is complete:
> one cleaner still assumes numeric activity hours before Pandera runs, and there is
> no schema registry, quarantine flow, or distribution monitoring.

Claims to avoid:

- "Built a production data-quality platform."
- "Guaranteed all data drift is detected."
- "Validated that the dataset is clinically trustworthy."
- "Added automatic schema evolution."

None is supported by this repository.

## 11. Position In The Close-out Plan

Task 3.3 is complete within its stated scope: three controlled malformed inputs,
their real failure layers, a reproducible report, focused regression tests, and an
honest record of the remaining cleaning-order hole now exist.

The next task is 3.4: shadow-run a candidate model beside the released model. That
is a serving experiment rather than a data-ingestion experiment. It will use the
same request, calculate two scores, return only the released score, and preserve the
comparison for later review.

