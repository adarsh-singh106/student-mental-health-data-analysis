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
first, then build and run:

```bash
# 1. Put the CSV in data/raw/ and verify it (prints instructions if missing)
python scripts/fetch_data.py

# 2. Build the container image
make build

# 3. Train a model (writes to ./artifacts) and serve the API on :8000
make train
make serve

# 4. Run the tests
make test
```

See `data/PROVENANCE.md` for where the dataset came from and how it is verified.
