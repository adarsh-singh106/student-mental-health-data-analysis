# Student Mental Health Score Prediction

This is an educational machine-learning project that predicts a `Mental_Health_Score` from student social-media and lifestyle inputs. It is a small FastAPI service backed by a scikit-learn pipeline, with reproducible model releases and an explicit quality gate. It is not a clinical instrument, a diagnostic tool, or evidence about real-world mental health outcomes.

## What The Model Earns

On a fixed audit split, predicting the training-set mean gives an MAE of **1.0536**. The RandomForest pipeline gives an MAE of **0.3519**, a **66.6% reduction**. That comparison is more informative than quoting the model score alone.

| Evaluation context | R2 | MAE | What it means |
|---|---:|---:|---|
| Mean baseline, fixed audit split | -0.0005 | 1.0536 | Predict the training-set mean for every row. |
| RandomForest, fixed audit split | 0.8574 | 0.3519 | A reproducible diagnostic comparison against the baseline. |
| Latest clean release, 5-fold CV gate | 0.8655 +/- 0.0089 | 0.3381 +/- 0.0085 | The measurement used to approve the local release. |

The audit split and release CV use different evaluation partitions, so their values are not interchangeable. The fixed split makes baseline, ablation, importance, and learning-curve comparisons repeatable; the release gate uses five folds after the final test holdout is separated.

## The Lucky-Split Correction

An earlier version reported R2 **0.890** from one 70/30 split. An audit of that earlier measurement found 5-fold R2 **0.8555 +/- 0.0111**; 0.890 was about three standard deviations above the cross-validated mean. The single split was favorable, not a reliable release criterion.

The current pipeline first reserves a final 20% test set, then gates releases using five-fold CV on the remaining 80%. The gate requires CV MAE mean plus one standard deviation to be below `0.40`; the threshold change and its evidence are documented in [ADR 0005](docs/decisions/0005-cv-gate-country-bucket-no-hpo.md). The historic 0.890 result is included here as a measurement failure that was corrected, not as the project result.

## What The Model Actually Uses

Permutation importance was measured on a held-out audit validation split with 10 repeats. It measures predictive dependence, not causation.

| Raw feature | Mean R2 drop when shuffled |
|---|---:|
| `Avg_Daily_Usage_Hours` | 0.9951 |
| `Sleep_Hours_Per_Night` | 0.2169 |
| `Country` | 0.0581 |
| `Daily_Unlocks` | 0.0466 |
| `Most_Used_Platform` | 0.0432 |
| `Study_Hours` | 0.0264 |
| `Purpose_Of_Use` | 0.0244 |
| `Physical_Activity_Hours` | 0.0189 |
| `Age` | 0.0187 |
| `Gender` | 0.0136 |
| `Academic_Level` | 0.0071 |
| `Stress_Level` | 0.0069 |

This is largely a two-variable model wearing twelve inputs: usage hours dominate, sleep is a distant second, and the remaining features contribute comparatively little. That finding is about this dataset and split; it is not a causal claim about mental health.

## Ablations

The same fixed audit split was used to remove feature blocks one at a time.

| Feature set | R2 | MAE | Delta R2 vs full |
|---|---:|---:|---:|
| Full pipeline | 0.8574 | 0.3519 | 0.0000 |
| Drop `Country` | 0.8378 | 0.3859 | -0.0197 |
| Drop `Stress_Level` | 0.8559 | 0.3528 | -0.0016 |
| Drop `Most_Used_Platform` | 0.8480 | 0.3656 | -0.0095 |
| Drop Country, platform, and purpose | 0.8072 | 0.4236 | -0.0502 |
| Drop `Age` | 0.8519 | 0.3586 | -0.0055 |

Country encoding earned its complexity: removing it costs 0.0197 R2. `Stress_Level` did not earn much in this model. The pipeline deliberately collapses rare, literal `Other`, and unseen countries into one `Other` bucket; see [ADR 0005](docs/decisions/0005-cv-gate-country-bucket-no-hpo.md). No hyperparameter search was run because the close-out goal is measurement integrity, not squeezing a small gain from this synthetic-looking dataset.

## Dataset Limitations

The data source is an undocumented secondary GitHub repository with no license. The CSV is not redistributed by this project, and it is used only for educational work. Full source, hash, and licensing details are in [data/PROVENANCE.md](data/PROVENANCE.md).

There are strong signs that the data was generated rather than measured:

- Only seven ages occur, and gender has exactly two categories.
- Whole-number target scores are overrepresented. For example, score 6.0 occurs 424 times, while 5.9 and 6.1 occur 134 and 119 times; that is a 3.35x concentration against its neighbors.
- The learning curve keeps improving from R2 0.7763 at 25% of the audit training data to 0.8574 at 100%.

The reasonable interpretation is that the model may be recovering a data-generating formula. It is not evidence that the same accuracy would transfer to real students, people, or clinical settings.

## Run It

Prerequisites: Git, Python 3.10, and [uv](https://docs.astral.sh/uv/). Docker is needed only to serve through the container.

The raw CSV is intentionally excluded because its license is unclear. After cloning, follow the manual placement instructions and verify the known hash:

```powershell
uv sync --frozen
uv run --frozen python scripts/fetch_data.py
```

When the script reports the file is missing, place it in `data/raw/` exactly as instructed, then rerun the verification command.

Create a model release and run tests:

```powershell
uv run --frozen python -m mental_health.models.release `
  --data-path "data/raw/Student Social Media And Mental Health Impact.csv" `
  --artifacts-root artifacts

uv run --frozen pytest
```

On systems with GNU Make, the equivalent shortcuts are:

```bash
make train
make test
make serve
```

`make serve` builds the code-only Docker image and mounts `artifacts/` read-only. The API exposes `GET /healthz` for process liveness, `GET /readyz` for model readiness, and `POST /predict` for validated predictions.

## Release Contract

Training does not silently overwrite a model. The release command performs this sequence:

```text
CSV path -> structural validation -> train -> CV gate -> publish artifact
```

Each release is versioned and contains:

```text
model.joblib
metadata.json
manifest.json
```

Metadata records the input SHA-256, source commit, dependency-lock digest, model parameters, metrics, gate result, and feature-schema version. The manifest records hashes and sizes for the model and metadata. The serving application verifies new-format artifacts before deserializing them, so a corrupt or incompatible artifact becomes a readiness failure rather than a silent prediction change.

The hashes detect accidental corruption. They are not a signature or a substitute for trusted artifact storage; never load an untrusted `joblib` file.

## Deliberately Not Built

| Not built | Why it would be theater here |
|---|---|
| Prometheus and Grafana dashboards | The project has no sustained real traffic. A dashboard nobody observes would be a screenshot, not operations. |
| Drift monitoring | The training data is one fixed CSV. Comparing it to itself would produce a flat line. |
| Scheduled retraining | Retraining on identical rows changes nothing meaningful. |
| Feature store | There are no timestamps, repeated entities, or shared online/offline feature computations to manage. |
| Canary or A/B rollout | There are no real users to split between models. |
| Autoscaling or Kubernetes | Traffic is generated only by a local load test, not a varying workload. |
| Queues and backpressure | The serving audit recorded zero errors through concurrency 64; there is no sustained overload to absorb. |
| Streaming ingestion | Nothing arrives continuously. |

These are explicit scope decisions, not a list of features waiting to be added. The request-path experiments that are real for this repository are tracked in [CLOSEOUT.md](CLOSEOUT.md).

## Evidence And Decisions

- [Model honesty audit](audit/REPORT_model.md): data forensics, baselines, ablations, permutation importance, and learning curve.
- [Decision records](docs/decisions/): preprocessing and measurement choices.
- [Close-out plan](CLOSEOUT.md): the bounded remaining work and stop condition.
