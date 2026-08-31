# ADR 0004 - Ship the evaluated 70% train-split artifact

**Status:** Accepted
**Date:** 2026-08-31
**Area:** model release / artifact governance

## Context

Current training flow:

1. `prepare_data()` cleans the raw CSV.
2. `train_test_split(..., test_size=0.30, random_state=42)` creates train and test sets.
3. The sklearn `Pipeline` is fitted only on `X_train` / `y_train`.
4. Metrics are computed on both train and test.
5. `gate(metrics)` decides whether the model is allowed to ship.
6. `save_artifact(pipeline, metrics, dataset)` saves the same fitted pipeline with metadata.

The accepted gate numbers are tied to this fitted object:

```text
train r2 ~= 0.9821
test  r2 ~= 0.8902
```

Before API/UI/deployment work, we had to decide whether the saved model should be:

- the exact model that passed the gate, trained on the 70% train split, or
- a freshly refitted model trained on 100% of the data after evaluation.

## Decision

Ship the exact model that passed the release gate.

That means the artifact saved to `artifacts/<version>/model.joblib` remains the
pipeline fitted on the training split. We do not refit on 100% of the dataset
before saving.

## Why

**1. Metadata stays true.** The metrics in `metadata.json` describe the same
model object that is saved on disk. If the pipeline is refitted on 100% of the
data after evaluation, the metadata would describe an older evaluated model, not
the final saved model.

**2. Gate and artifact point to one thing.** The release rule is simple:

```text
model passes gate -> same model is saved
model fails gate  -> no artifact is saved
```

This is easier to explain, test, debug, and defend in an interview.

**3. Reproducibility matters more than a small possible accuracy gain.** Refit on
100% might improve the deployed model slightly because it sees more data, but it
also removes the direct link between measured test performance and the saved
artifact.

## Rejected Option

### Refit on 100% data before saving

Rejected for now.

The benefit is that the final model trains on all available labeled data. The
cost is that the recorded test metrics no longer belong to the saved model.
That creates audit confusion:

```text
metadata metrics -> evaluated 70% train-split model
model.joblib      -> different 100% refitted model
```

For this project, that tradeoff is not worth it.

## Consequences

- The API will load a model whose metrics honestly describe the saved artifact.
- `save_artifact()` can stay dumb: it saves the fitted pipeline it receives.
- The release command should keep the order `train -> gate -> save`.
- If we later want a 100% refit flow, it needs a separate documented release
  strategy, for example cross-validation metrics plus explicit metadata saying
  the final artifact was refitted on the full dataset.

## General Lesson

Deployment is not only about getting the highest possible score. It is also
about being able to answer:

```text
Which exact model is this?
Which exact data trained it?
Which exact metrics justified shipping it?
```

For now, the clean answer is: the shipped artifact is the same fitted pipeline
that passed the gate.
