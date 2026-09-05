import json
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor

from mental_health.models.save import save_artifact


# Make dummy fitted - Pipeline
def make_fitted_pipe():
    # Features
    X = pd.DataFrame({
        "a":[1.0, 2.0, 3.0],
        "b":[4.0, 5.0, 6.0]
    })

    # Target
    y = [1.0, 2.0, 3.0]

    # Dummy Pipeline
    pipe = Pipeline([
        ("prep", StandardScaler()),
        ("model", RandomForestRegressor(n_estimators=3,random_state=42))
    ])
    pipe.fit(X,y) # fit zaroori — warna get_feature_names_out() phategi

    return pipe

def test_save_artifact_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr("mental_health.models.save._git_dirty", lambda: False) # Don't Ask git
    monkeypatch.setattr("mental_health.models.save._git_commit", lambda: "test-commit") # git binary bhi mat maango
    pipe = make_fitted_pipe()
    metrics = {"train": {"r2": 0.98}, "test": {"r2": 0.89}}
    dataset = {"file": "x.csv", "rows": 3, "sha256": "abc"}

    save_artifact(pipe, metrics, dataset, artifacts_root=tmp_path)

    # Assert : if file exists
    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    folder = run_dirs[0]

    assert (folder / "model.joblib").exists()
    assert (folder / "metadata.json").exists()
    assert (tmp_path / "latest.txt").read_text() == folder.name

    # Assert : content of metadata.json
    meta = json.loads((folder / "metadata.json").read_text())
    assert meta["target"] == "Mental_Health_Score"
    assert meta["features"]["count"] == 2      # a, b → 2 columns
    assert meta["gate"]["passed"] is True
    assert meta["metrics"] == metrics
    