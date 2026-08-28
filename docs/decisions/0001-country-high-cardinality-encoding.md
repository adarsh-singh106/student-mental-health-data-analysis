# ADR 0001 — Encoding high-cardinality `Country`

**Status:** Accepted
**Date:** 2026-08-28
**Area:** feature engineering / preprocessing

## Context

`Country` has ~111 unique values in the dataset. We cannot one-hot encode it
directly — that would create 110+ mostly-empty columns (high cardinality),
which adds noise and hurts the model. Dropping `Country` also loses real signal
(country correlates with culture, sleep norms, internet access).

The notebook prototype solved this by:

```python
top_countries = df['Country'].value_counts().index[:10]   # learned from FULL data
df['Grouped_country'] = df['Country'].apply(group_countries)  # applied BEFORE split
```

This has **two production bugs**:
1. **Train-serve skew** — the top-10 list is *learned from data* (a stateful
   transform) but lives *outside* the model pipeline. At serving time the API
   has no idea what the top-10 were, so it cannot reproduce the transform.
2. **Data leakage** — the top-10 were computed on the *entire* dataset,
   including test rows, before the train/test split.

The fix for both: the grouping must be a **stateful step inside the pipeline,
fit on the training set only**, so it travels with the saved artifact.

There are two valid ways to do that.

## Options considered

### Option A — built-in `OneHotEncoder` frequency bucketing (chosen)

```python
OneHotEncoder(handle_unknown="infrequent_if_exist", max_categories=11)
```

- `fit` (train only): counts category frequencies, keeps the most common,
  folds the rest into one `infrequent` bucket.
- `transform`: known category → its column; anything else → infrequent bucket.
- Native since scikit-learn 1.1. No custom code.

### Option B — custom `CountryGrouper` transformer

```python
class CountryGrouper(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None): ...   # learn + store top-N from train
    def transform(self, X): ...     # map non-top-N -> "Other"
```
Then a plain `OneHotEncoder` after it.

- Full control over the logic; teaches the custom-transformer pattern.
- More code, and requires its own unit tests.

## Which performs better?

**Predictively, they are ~identical.** Both cut `Country` down to ~11 buckets
before one-hot encoding, and a Random Forest does not care whether the leftover
bucket is called `"Other"` or `"infrequent_sklearn"`. Any R²/MAE difference
would be noise, not signal. So performance is **not** the deciding factor here.

If you ever want to prove it empirically: train the exact same pipeline twice
(only this step swapped), compare test R² and MAE on the same split/seed. You
will find them within rounding distance. Don't spend your 2 days on this.

The real difference is **engineering cost**, not accuracy:

| Axis | Option A (built-in) | Option B (custom) |
|------|--------------------|-------------------|
| Lines of code | ~1 | ~20 + tests |
| Correctness | library-guaranteed | you must get `fit`/`transform` right |
| Handles unseen countries at serve time | yes, natively | you must handle it |
| Teaches custom-transformer skill | no | yes |
| Maintenance | none | yours forever |

## Industry standard

The universal principle: **use the framework's built-in feature when one exists;
write a custom transformer only when the logic is genuinely bespoke.** Frequency
bucketing is a solved, common problem — so the built-in `OneHotEncoder`
(`min_frequency` / `max_categories`) is the modern standard. Custom
`BaseEstimator`/`TransformerMixin` transformers are standard and expected when
you need logic sklearn does *not* provide (domain rules, external lookups, etc.).

Either way, the non-negotiable part is the same: **the stateful step lives inside
the pipeline and is fit on train only.** That is what prevents skew and leakage,
and it is what actually matters in an interview or a code review.

## Decision

**Option A.** For this project it is production-correct, near-zero code, and
library-tested. It frees the time budget for the parts that teach more (release
gate, artifact + metadata, serving). Revisit only if we later need grouping
logic that `OneHotEncoder` cannot express.

## Consequences

- Delete `top_countries` and `group_countries` from the pipeline entirely; feed
  raw `Country` straight into the encoder.
- The infrequent-bucket vocabulary is now stored in the fitted pipeline, so
  training and serving use identical logic automatically.
- We lose the explicit custom-transformer learning exercise; noted, acceptable
  under the deadline.
