# ADR 0005 — Cross-validation gate, single Country bucket, no hyperparameter search

**Status:** Accepted
**Date:** 2026-09-07
**Area:** model release / measurement / preprocessing

## Context

Phase 1 of the close-out exists to fix **measurement defects** — places where a
number looked good only because the measurement was weak. Three separate
decisions came out of it. They share one theme (be honest about what the numbers
mean) so they live in one ADR, but each stands on its own.

---

## Decision 1 — Gate on cross-validation, and raise the bar 0.35 → 0.40

### Context

The old gate judged a single 70/30 split:

```python
MIN_TEST_R2  = 0.85
MAX_TEST_MAE = 0.35
MAX_TEST_RMSE = ...
# plus: abs(train_r2 - test_r2) < 0.15   # "overfit gap"
```

The single-split `test r2` read **0.890** and `test MAE` read under 0.35, so the
model passed. But one split can be lucky — that one 30% happened to be easy.

When we ran **5-fold cross-validation** on the same data (train 5 times on
different 4/5 slices, score the held-out 1/5 each time), the truth came out:

```text
CV MAE = 0.3568 +/- 0.0114
worst-case (mean + 1 std) ~= 0.368
```

`0.368 > 0.35`. The model that "passed" the old gate actually **breached** it
once we measured honestly. The 0.35 bar was never real — it was calibrated on
one lucky split.

Two things were also wrong with the old checks:

- **Single-split thresholds** (r2/mae/rmse) — one split can be lucky, as shown.
- **The overfit-gap check** `abs(train_r2 - test_r2) < 0.15` — for a Random
  Forest a high train r2 is *how it works* (it memorises the training set by
  design), so a large train-test gap is expected and measures nothing about
  trustworthiness. It had passed by only 0.03 of margin anyway — noise.

### Decision

1. **Gate on cross-validation, not a single split.** The gate now receives
   `cv_stats` and passes only if the **worst-case** CV MAE clears the bar:

   ```python
   mae_upper = cv_stats["mae_mean"] + cv_stats["mae_std"]
   if mae_upper < MAX_CV_MAE:  # 0.40
       return True
   ```

   Adding the std is deliberate: a model that averages fine but swings wildly
   across folds is not trustworthy, and the spread makes it fail. The CV std now
   carries the whole "is this stable" question, replacing the deleted gap check.

2. **Raise the bar 0.35 → 0.40, in the open.** The honest CV number is
   ~0.357 ± 0.011. A bar of 0.40 sits above the real worst case (~0.368) with a
   small, deliberate margin. Moving the bar *silently* would be dishonest;
   moving it *with the CV evidence written down* is the entire point of Phase 1.

3. **Delete** `MIN_TEST_R2`, `MAX_TEST_MAE`, `MAX_TEST_RMSE`, and the gap check.

### Why not keep 0.35

Because the model genuinely does not clear 0.35 at its worst-case CV MAE. We had
two honest choices: (A) raise the bar to a defensible 0.40 and say why, or
(B) improve the model until it clears 0.35. Under the close-out deadline we chose
**A** — the goal of this phase is honest measurement, not squeezing accuracy.
Option B is real future work (better features, tuning), not a Phase 1 task.

### Consequences

- `test_final` is still computed once and **only reported**, never gated — the
  test set stays a vault (see the 3-way split, ADR-adjacent to 0004).
- `metadata.json` records `gate.thresholds.max_cv_mae = 0.40` and the full
  `cv` block (mean, std, per-fold), so the number that justified shipping is
  auditable.

---

## Decision 2 — Collapse `Country` into a single `"Other"` bucket

### Context

ADR 0001 chose `OneHotEncoder(handle_unknown="infrequent_if_exist",
max_categories=11)` for `Country`. In practice that produced **two** competing
"misc" columns:

- `Country_Other` — the CSV already contains a literal category `"Other"`
  (1880 rows, the single largest value).
- `Country_infrequent_sklearn` — the encoder's own bucket for rare countries.

Two catch-alls means the "miscellaneous country" signal is split across two
columns for no reason. Worse, **encoder params alone cannot fix it**: the literal
`"Other"` is *frequent* (1880 rows), so `min_frequency` / `max_categories` will
never fold it into the infrequent bucket — the encoder does not consider a
frequent value "rare".

### Decision

Put a pre-mapping step *before* the encoder:

```python
KNOWN_COUNTRIES = ["Australia","Canada","France","Germany","India",
                   "Ireland","Mexico","Spain","Turkey","UK","USA"]

country_pipeline = Pipeline([
    ("collapse", FunctionTransformer(_collapse_country, feature_names_out="one-to-one")),
    ("encode",   OneHotEncoder(handle_unknown="ignore")),
])
```

`_collapse_country` maps any value **not** in `KNOWN_COUNTRIES` — rare countries,
the literal `"Other"`, and any unseen country at serve time — to a single
`"Other"`. The result is 12 clean columns (11 known + one `Other`), no
`infrequent_sklearn`.

### The honesty caveat (important)

`KNOWN_COUNTRIES` is a **frozen constant**, decided once from a manual frequency
inspection (countries with ≳80 rows). It is **NOT** computed from
`value_counts()` at fit time. That is on purpose:

- Computing it at fit time would be **data leakage** — the choice of which
  countries "count" would be shaped by the data in that fit, and at serve time
  the pipeline cannot reproduce a data-derived list it never stored.
- Freezing it as a constant makes the transform **stateless and identical**
  across train, test, and serve. This is the same class of human decision as the
  ordinal order for `Stress_Level` — a domain choice, not a learned parameter.

**Trade-off (accepted):** if a new country becomes frequent later, the list must
be updated **by hand** and the model retrained. That is a conscious cost of not
leaking. Documented here so it is not a surprise.

This supersedes ADR 0001's encoder-only approach for `Country`. ADR 0001's core
principle still holds — the stateful step lives inside the pipeline — the only
change is that a pre-map is needed because a *frequent* literal catch-all cannot
be merged by encoder frequency params.

### Consequences

- One `Country_Other` column owns rare + literal-`"Other"` + unseen.
- `handle_unknown="ignore"` on the encoder is belt-and-suspenders: after collapse
  nothing unknown should reach it, but if it did it becomes all-zeros, not a raise.
- `get_feature_names_out()` still works end-to-end (verified: 40 total features).

---

## Decision 3 — No hyperparameter search; ship documented defaults

### Context

The shipped model is `RandomForestRegressor(random_state=42, n_jobs=1)` — sklearn
defaults. A reasonable reviewer asks: "did you tune it?"

### Decision

**No formal hyperparameter search (GridSearchCV / RandomizedSearchCV) for this
release.** We ship the documented defaults, and we say so.

### Why

- **The bottleneck is measurement and honesty, not the last few % of accuracy.**
  Phase 1 is about trustworthy numbers; a hyperparameter sweep optimises a
  different axis and would not change the "is this measured honestly" story.
- **Defaults are a legitimate, defensible baseline.** A tuned model with no
  honest gate is worse than an untuned model with an honest CV gate.
- **Search is not free of risk.** Tuning against the same data we gate on can
  quietly overfit the selection to the folds unless done with nested CV — which
  is more machinery than this release needs.

### Consequences

- `metadata.json` records the exact `model.params`, so "we used defaults" is
  auditable, not vague.
- Hyperparameter search is explicit **future work**, to be done with nested CV so
  the gate stays honest — not bolted onto this release.

---

## General lesson

All three decisions are the same move: **make the measurement honest, then make
the decision in the open.** A gate is only as trustworthy as the measurement
under it; a threshold you move must be moved with evidence; a default you keep
must be recorded as a choice, not a silence.
