# Student Mental Health — Score Prediction

An **educational / portfolio** machine-learning project that predicts a
`Mental_Health_Score` (0–10) from student social-media and lifestyle features,
served behind a small FastAPI app. It is **not** a clinical instrument.

> **Note:** This is a placeholder README. The full write-up — honest results
> against the baseline, the lucky-split story, what the model actually uses,
> the data-quality caveats, and what was deliberately not built — lands in
> close-out **Phase 2**. See `CLOSEOUT.md`.

## Quickstart

The dataset is not redistributed here (its source has no license). Place it
first, then train and run:

```bash
# 1. Put the CSV in data/raw/ and verify it (prints instructions if missing)
python scripts/fetch_data.py

# 2. Train a model on the host — writes to ./artifacts (needs a clean git tree)
make train

# 3. Serve the trained model from a container on http://localhost:8000
make serve

# 4. Run the tests
make test
```

Training and tests run on the host (need `uv`); serving runs in a container
(needs Docker). Training is on the host on purpose: it records the git commit
into the model's metadata, which only makes sense inside a real git repo — the
shipped image carries none. The reasoning is written out in the `Makefile`.

See `data/PROVENANCE.md` for where the dataset came from and how it is verified.

To override the default input or artifact location without editing source:

```bash
make train DATA_PATH="C:/data/input.csv" ARTIFACTS_ROOT="C:/model-releases"
```

## Release Contract

`make train` runs an explicit release boundary:

```text
CSV path -> prepare -> train -> CV gate -> immutable artifact directory
```

Each newly published directory contains `model.joblib`, `metadata.json`, and
`manifest.json`. Metadata records the source commit, input SHA-256,
dependency-lock digest, metrics, model parameters, and feature-schema version.
The manifest records SHA-256 and byte-size facts for the model and metadata.

The release is assembled in a staging directory, then published before
`latest.txt` moves to it. Serving verifies a new-format manifest before model
deserialization, so a modified or incomplete artifact becomes a readiness
failure rather than a silent prediction change. These hashes detect accidental
corruption; artifact storage must still be trusted because a hash is not a
signature.

### Running Without Make

`make` is optional convenience tooling. On Windows PowerShell or any machine
without GNU Make, use the underlying commands directly:

```powershell
uv run --frozen python -m mental_health.models.release `
  --data-path "data/raw/Student Social Media And Mental Health Impact.csv" `
  --artifacts-root artifacts

uv run --frozen pytest
```
