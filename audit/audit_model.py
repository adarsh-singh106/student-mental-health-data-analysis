"""Read-only honesty audit of the training pipeline.

Run from repo root:   uv run python audit/audit_model.py
Writes:               audit/REPORT_model.md
Touches nothing in src/, data/ or artifacts/.

Every number this prints is one an interviewer can ask you for.
"""

from __future__ import annotations

import csv
import collections
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mental_health.data.preparation import prepare_data  # noqa: E402
from mental_health.features.preprocessing import build_preprocessor  # noqa: E402

CSV = ROOT / "data" / "raw" / "Student Social Media And Mental Health Impact.csv"
TARGET = "Mental_Health_Score"
SEED = 42
OUT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def row(label: str, m: dict[str, float]) -> str:
    return f"| {label:38s} | {m['r2']:7.4f} | {m['mae']:7.4f} | {m['rmse']:7.4f} |"


# ----------------------------------------------------------------------------
# 1. RAW DATA FORENSICS  — is this dataset real, or generated?
# ----------------------------------------------------------------------------
def section_data_forensics() -> None:
    say("## 1. Raw data forensics")
    say()
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    say(f"Rows in raw CSV: **{len(rows)}**")
    tup = [tuple(r.values()) for r in rows]
    say(f"Exact duplicate rows: **{len(tup) - len(set(tup))}** "
        f"(train.py calls remove_duplicates, so training sees {len(set(tup))})")
    say()

    say("### Cardinality of every column")
    say()
    say("| column | distinct | verdict flag |")
    say("|---|---|---|")
    for k in rows[0]:
        vals = {r[k] for r in rows}
        flag = ""
        if k == "Age" and len(vals) <= 10:
            flag = "suspiciously few for a real survey"
        if k == "Gender" and len(vals) == 2:
            flag = "no third option — unusual for real 2020s survey data"
        say(f"| {k} | {len(vals)} | {flag} |")
    say()

    say("### Does the literal string 'Other' exist as a Country value?")
    say()
    countries = {r["Country"] for r in rows}
    has_other = "Other" in countries
    say(f"`'Other' in Country`: **{has_other}**  (distinct countries: {len(countries)})")
    if has_other:
        say()
        say("> If True, this is a real bug. `preprocessing.py` uses "
            "`OneHotEncoder(handle_unknown='infrequent_if_exist', max_categories=11)`, "
            "which creates its own `Country_infrequent_sklearn` bucket. You now have "
            "**two** catch-all buckets competing: the literal `Other` category from the "
            "CSV and sklearn's infrequent bucket. metadata.json shows both feature names.")
    say()

    say("### Target granularity — the generated-data tell")
    say()
    y = [float(r[TARGET]) for r in rows]
    cnt = collections.Counter(y)
    say(f"min={min(y)}  max={max(y)}  mean={np.mean(y):.4f}  std={np.std(y):.4f}  "
        f"distinct={len(cnt)}")
    say()
    say("| score | count | count at -0.1 | count at +0.1 | ratio vs neighbours |")
    say("|---|---|---|---|---|")
    for v in sorted({round(x) for x in y}):
        c = cnt.get(float(v), 0)
        lo, hi = cnt.get(round(v - 0.1, 1), 0), cnt.get(round(v + 0.1, 1), 0)
        nb = (lo + hi) / 2 or 0.5
        if c:
            say(f"| {v:.1f} | {c} | {lo} | {hi} | **{c / nb:.2f}x** |")
    say()
    say("> A real 1-decimal instrument has no reason to pile up on whole integers. "
        "A large ratio here means whole-number scores were emitted by one code path "
        "and fractional ones by another — i.e. the column was generated, not measured.")
    say()


# ----------------------------------------------------------------------------
# 2. WHAT THE MODEL ACTUALLY EARNS OVER A TRIVIAL BASELINE
# ----------------------------------------------------------------------------
def section_baselines(X_tr, y_tr, X_va, y_va):
    say("## 2. What the model earns over trivial baselines")
    say()
    say("All rows below are fit on the SAME train split and scored on the SAME")
    say("validation split. `train.py` reports 0.890 r2 — the question is how much")
    say("of that a five-line model already gives you for free.")
    say()
    say("| model | val r2 | val MAE | val RMSE |")
    say("|---|---|---|---|")

    results = {}
    candidates = {
        "DummyRegressor(mean)": DummyRegressor(strategy="mean"),
        "LinearRegression": LinearRegression(),
        "DecisionTree(max_depth=3)": DecisionTreeRegressor(max_depth=3, random_state=SEED),
        "DecisionTree(max_depth=6)": DecisionTreeRegressor(max_depth=6, random_state=SEED),
        "RandomForest — YOUR config": RandomForestRegressor(random_state=SEED, n_jobs=1),
        "RandomForest(min_samples_leaf=5)": RandomForestRegressor(
            min_samples_leaf=5, random_state=SEED, n_jobs=1),
        "RandomForest(min_samples_leaf=20)": RandomForestRegressor(
            min_samples_leaf=20, random_state=SEED, n_jobs=1),
    }
    for name, est in candidates.items():
        pipe = Pipeline([("prep", build_preprocessor()), ("model", est)])
        pipe.fit(X_tr, y_tr)
        m = metrics(y_va, pipe.predict(X_va))
        results[name] = m
        say(row(name, m))
    say()

    dummy = results["DummyRegressor(mean)"]
    yours = results["RandomForest — YOUR config"]
    lin = results["LinearRegression"]
    stump = results["DecisionTree(max_depth=3)"]
    say(f"- Predicting the mean gives MAE **{dummy['mae']:.4f}**. Your model gives "
        f"**{yours['mae']:.4f}** — a **{(1 - yours['mae'] / dummy['mae']) * 100:.1f}%** "
        "reduction. That is the only honest way to state the result.")
    say(f"- LinearRegression reaches **{lin['r2'] / yours['r2'] * 100:.1f}%** of your "
        f"r2. A depth-3 tree reaches **{stump['r2'] / yours['r2'] * 100:.1f}%**.")
    say("- If those percentages are high, the ensemble is not where your value is, "
        "and 'RandomForest' is not the interesting sentence on your resume.")
    say()
    return results


# ----------------------------------------------------------------------------
# 3. ABLATIONS — what did each block of feature work actually buy?
# ----------------------------------------------------------------------------
def section_ablations(X_tr, y_tr, X_va, y_va, baseline_r2: float):
    say("## 3. Ablations — what each block of feature engineering bought")
    say()
    say("ADR 0001 spends real effort on encoding 111 countries. This measures it.")
    say()
    say("| feature set | val r2 | val MAE | delta r2 vs full |")
    say("|---|---|---|---|")

    groups = {
        "FULL (all 12 raw columns)": [],
        "drop Country": ["Country"],
        "drop Stress_Level": ["Stress_Level"],
        "drop Most_Used_Platform": ["Most_Used_Platform"],
        "drop Country + Platform + Purpose": ["Country", "Most_Used_Platform", "Purpose_Of_Use"],
        "drop Age": ["Age"],
    }
    for label, dropped in groups.items():
        keep = [c for c in X_tr.columns if c not in dropped]
        prep = build_preprocessor()
        prep.transformers = [
            (n, t, [c for c in cols if c in keep])
            for n, t, cols in prep.transformers
            if [c for c in cols if c in keep]
        ]
        pipe = Pipeline([("prep", prep),
                         ("model", RandomForestRegressor(random_state=SEED, n_jobs=1))])
        pipe.fit(X_tr[keep], y_tr)
        m = metrics(y_va, pipe.predict(X_va[keep]))
        say(f"| {label:38s} | {m['r2']:7.4f} | {m['mae']:7.4f} | {m['r2'] - baseline_r2:+7.4f} |")
    say()
    say("> Any row whose delta is near zero is feature work that earned nothing. "
        "Say so in the README rather than letting an interviewer find it.")
    say()


# ----------------------------------------------------------------------------
# 4. THE OVERFIT QUESTION gate.py IS ASKING WRONG
# ----------------------------------------------------------------------------
def section_overfit(X_tr, y_tr, X_va, y_va):
    say("## 4. The overfitting check in gate.py")
    say()
    pipe = Pipeline([("prep", build_preprocessor()),
                     ("model", RandomForestRegressor(random_state=SEED, n_jobs=1))])
    pipe.fit(X_tr, y_tr)
    tr, va = metrics(y_tr, pipe.predict(X_tr)), metrics(y_va, pipe.predict(X_va))
    say(f"train: r2={tr['r2']:.4f} mae={tr['mae']:.4f}")
    say(f"val:   r2={va['r2']:.4f} mae={va['mae']:.4f}")
    say()
    say(f"- `gate.py` statistic: `abs(train_r2 - val_r2)` = **{abs(tr['r2'] - va['r2']):.4f}** "
        f"vs threshold 0.15 -> **{'PASSES' if abs(tr['r2']-va['r2'])<0.15 else 'FAILS'}**")
    say(f"- MAE ratio val/train = **{va['mae'] / tr['mae']:.2f}x**")
    say()
    say("> These two statistics disagree. r2 is bounded and compresses differences at "
        "the top of its range, so a large relative error gap can still show a small "
        "r2 gap. `RandomForestRegressor()` defaults to `max_depth=None, "
        "min_samples_leaf=1` — it grows every tree until leaves are pure, so a very "
        "high train r2 is memorisation, not fit quality. The MAE ratio is the "
        "diagnostic that sees it.")
    say()


# ----------------------------------------------------------------------------
# 5. CROSS-VALIDATION — the number that is missing from the repo entirely
# ----------------------------------------------------------------------------
def section_cv(X_tr, y_tr):
    say("## 5. Cross-validated estimate (absent from the repo)")
    say()
    pipe = Pipeline([("prep", build_preprocessor()),
                     ("model", RandomForestRegressor(random_state=SEED, n_jobs=1))])
    kf = KFold(n_splits=5, shuffle=True, random_state=SEED)
    scores = cross_val_score(pipe, X_tr, y_tr, cv=kf, scoring="r2")
    mae = -cross_val_score(pipe, X_tr, y_tr, cv=kf, scoring="neg_mean_absolute_error")
    say(f"5-fold r2 on the train split:  mean **{scores.mean():.4f}**  "
        f"std **{scores.std():.4f}**  folds {np.round(scores, 4).tolist()}")
    say(f"5-fold MAE on the train split: mean **{mae.mean():.4f}**  std **{mae.std():.4f}**")
    say()
    say(f"> Report `{scores.mean():.3f} +/- {scores.std():.3f}` instead of a bare "
        "point estimate. A single split gives you one draw from this distribution, "
        "and `gate.py` currently promotes or blocks a model on that one draw.")
    say()


# ----------------------------------------------------------------------------
# 6. PERMUTATION IMPORTANCE on held-out data
# ----------------------------------------------------------------------------
def section_importance(X_tr, y_tr, X_va, y_va):
    say("## 6. Permutation importance (validation split, 10 repeats)")
    say()
    pipe = Pipeline([("prep", build_preprocessor()),
                     ("model", RandomForestRegressor(random_state=SEED, n_jobs=1))])
    pipe.fit(X_tr, y_tr)
    r = permutation_importance(pipe, X_va, y_va, n_repeats=10,
                              random_state=SEED, scoring="r2", n_jobs=1)
    say("| raw column | mean r2 drop when shuffled | std |")
    say("|---|---|---|")
    order = np.argsort(r.importances_mean)[::-1]
    for i in order:
        say(f"| {X_va.columns[i]} | {r.importances_mean[i]:+.4f} | {r.importances_std[i]:.4f} |")
    say()
    say("> Columns at or below zero contribute nothing on unseen data. This is "
        "computed on raw columns, so it answers the interview question directly: "
        "*which inputs actually matter, and how do you know?*")
    say()


# ----------------------------------------------------------------------------
# 7. LEARNING CURVE — would more data help, or is the ceiling structural?
# ----------------------------------------------------------------------------
def section_learning_curve(X_tr, y_tr, X_va, y_va):
    say("## 7. Learning curve")
    say()
    say("| train fraction | n rows | val r2 | val MAE |")
    say("|---|---|---|---|")
    for frac in (0.25, 0.50, 0.75, 1.00):
        n = int(len(X_tr) * frac)
        pipe = Pipeline([("prep", build_preprocessor()),
                         ("model", RandomForestRegressor(random_state=SEED, n_jobs=1))])
        pipe.fit(X_tr.iloc[:n], y_tr.iloc[:n])
        m = metrics(y_va, pipe.predict(X_va))
        say(f"| {frac:.0%} | {n} | {m['r2']:.4f} | {m['mae']:.4f} |")
    say()
    say("> If val r2 has flattened by 75%, more rows will not help and the remaining "
        "error is irreducible noise in the target. That is the honest ceiling.")
    say()


def main() -> None:
    say("# Model honesty audit")
    say()
    say(f"Generated by `audit/audit_model.py` — python {platform.python_version()}, "
        f"seed {SEED}. Read-only: nothing in `src/`, `data/` or `artifacts/` is modified.")
    say()

    section_data_forensics()

    df = prepare_data(CSV)
    X, y = df.drop(columns=[TARGET]), df[TARGET]

    # THREE-way split. train.py only makes two, which is the core methodology defect:
    # it selects on the same split it reports.
    X_tmp, X_te, y_tmp, y_te = train_test_split(X, y, test_size=0.20, random_state=SEED)
    X_tr, X_va, y_tr, y_va = train_test_split(X_tmp, y_tmp, test_size=0.25, random_state=SEED)
    say("## Splits used by this audit")
    say()
    say(f"train **{len(X_tr)}** / validation **{len(X_va)}** / test **{len(X_te)}** "
        "(test is fit-once and deliberately untouched below)")
    say()
    say("> `train.py` makes a single 70/30 split, computes metrics on the 30%, then "
        "hands those metrics to `gate()` which decides whether to save. The split it "
        "reports is the split it selects on, so `test r2 = 0.890` in metadata.json is "
        "a selection score, not a held-out score. Every re-run after a failed gate "
        "leaks a little more.")
    say()

    res = section_baselines(X_tr, y_tr, X_va, y_va)
    section_ablations(X_tr, y_tr, X_va, y_va, res["RandomForest — YOUR config"]["r2"])
    section_overfit(X_tr, y_tr, X_va, y_va)
    section_cv(X_tr, y_tr)
    section_importance(X_tr, y_tr, X_va, y_va)
    section_learning_curve(X_tr, y_tr, X_va, y_va)

    say("## Artifact provenance")
    say()
    latest = (ROOT / "artifacts" / "latest.txt")
    if latest.exists():
        v = latest.read_text().strip()
        meta = json.loads((ROOT / "artifacts" / v / "metadata.json").read_text())
        say(f"- `latest.txt` -> `{v}`")
        say(f"- recorded commit `{meta['git']['commit'][:12]}`, "
            f"**dirty = {meta['git']['dirty']}**")
        if meta["git"]["dirty"]:
            say("- > `dirty: true` means the working tree had uncommitted changes when "
                "this model was trained. The commit hash in the artifact therefore does "
                "**not** identify the code that produced it, so the provenance record "
                "you built cannot be used to reproduce the model. `save_artifact` should "
                "refuse to write when the tree is dirty.")
    say()

    out = ROOT / "audit" / "REPORT_model.md"
    out.write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n>>> wrote {out}")


if __name__ == "__main__":
    main()
