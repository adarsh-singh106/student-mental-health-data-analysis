# ADR 0002 — No imputers in the preprocessing pipeline

**Status:** Accepted
**Date:** 2026-08-28
**Area:** feature engineering / preprocessing, API contract

## Context

An **imputer** fills in a missing value with a guess — for example, if a
student's `Sleep_Hours_Per_Night` is blank, `SimpleImputer(strategy="mean")`
quietly replaces it with the average sleep hours from training data. The point
is to stop a missing value from crashing the model.

The notebook's markdown claimed *"We include a `SimpleImputer` in every branch...
a pipeline that assumes 'no missing values ever' is a pipeline that breaks in
production."* But the actual notebook code had **no imputer anywhere**. So the
text and the code disagreed, and we had to actually decide.

Facts we had:
- The dataset has **zero** missing values in all 13 columns (`df.isnull().sum()`).
- Our Pandera schema does not allow nulls, so training data with holes is
  rejected before it reaches the model.
- The future FastAPI layer will validate every request with Pydantic.

## Options considered

### Option 1 — Add `SimpleImputer` to every branch

Missing numeric → filled with the mean. Missing category → filled with the most
frequent value. Nothing ever crashes.

### Option 2 — No imputers; require complete input (chosen)

Any row reaching the model must have every field. Incomplete data is rejected
earlier — by Pandera during training, by Pydantic at the API.

## The trade-off in plain words

| | Option 1 (imputers) | Option 2 (no imputers) |
|---|---|---|
| Missing value arrives | silently filled with a guess | request is **rejected** |
| Failure style | never fails — always answers | fails loudly and early |
| Risk | returns a confident prediction built on **invented** data | user gets a 4xx error and must resend |
| Extra code | one step per branch | none |

The important point: **an imputer is not free safety — it is a guess.** If a
student's sleep hours are missing and we fill in "6.6 hours (the average)", the
model still returns a confident mental-health score based on data nobody
provided. For a health-adjacent prediction, a wrong-but-confident answer is
worse than an honest error. Option 1 trades a visible failure for an invisible
one.

## Decision

**Option 2 — no imputers.** Missing data is a *contract violation*, not
something to paper over. We reject it at the boundary instead of guessing.

## Consequences (this is the part that matters)

Skipping the safety net means the guarantee moves somewhere else. It is now a
**load-bearing assumption**:

> Every field must be **required** in the Pydantic request model.

If we ever make a field optional, here is exactly what happens:
`None` → `StandardScaler` passes it through as `NaN` → `RandomForest.predict()`
raises → `/predict` returns a 500 for what should have been a clean 400.

So:
- **Every** field in the Pydantic model is required. No `Optional`, no defaults.
- Pandera already blocks nulls in training data, so training is covered too.
- If a future data source genuinely starts sending incomplete rows, we revisit
  this ADR, add imputers deliberately, and retrain — we do not patch it at the
  API layer.

## The generalizable principle

**A safety net you skip becomes an assumption someone downstream must uphold.**
Skipping it is fine. Forgetting that you skipped it is what breaks systems. That
is the entire reason this document exists — so the assumption is written down
instead of living in one person's memory.

Related: [ADR 0001](0001-country-high-cardinality-encoding.md) — same theme,
keeping the model's real requirements explicit rather than implicit.
