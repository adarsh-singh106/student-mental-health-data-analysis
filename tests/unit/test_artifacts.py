import pytest
from mental_health.api.artifacts import load_latest_artifact, ArtifactLoadError

import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from mental_health.models.save import save_artifact

# A. Raise tests (No real Model or Pipeline required)

# check "ArtifactLoadError" deta h ya nhi ! when it found no latest.txt in given artifact_root Path
def test_missing_latest_txt_raises(tmp_path):
    # tmp_path khaali hai → latest.txt hai hi nahi
    with pytest.raises(ArtifactLoadError):
        load_latest_artifact(tmp_path)


# same check bas is bar file h but empty hone per
# error de rha h ya nhi
def test_empty_latest_txt_raises(tmp_path):
    (tmp_path / "latest.txt").write_text("")   # khaali pointer
    with pytest.raises(ArtifactLoadError):
        load_latest_artifact(tmp_path)

# latest.txt mai jab read kiya and us naam ka folder mila he nhi tab error de rha h ya nhi
def test_version_dir_missing_raises(tmp_path):
    (tmp_path / "latest.txt").write_text("v1")  # par tmp_path/v1 dir banaya hi nahi
    with pytest.raises(ArtifactLoadError):
        load_latest_artifact(tmp_path)


# same check  folder h but empty h, koi files nhi 
def test_model_file_missing_raises(tmp_path):
    (tmp_path / "latest.txt").write_text("v1")
    (tmp_path / "v1").mkdir()                    # dir hai, par andar model.joblib nahi
    with pytest.raises(ArtifactLoadError):
        load_latest_artifact(tmp_path)

# B. Happy-path (save → load round-trip) : Model / Pipeline Required


# Make a dummy pipeline jis mai ye do steps ho "prep" & "model"
def make_fitted_pipe():
    X = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
    y = [1.0, 2.0, 3.0]
    pipe = Pipeline([
        ("prep", StandardScaler()),
        ("model", RandomForestRegressor(n_estimators=3, random_state=42)),
    ])
    pipe.fit(X, y)
    return pipe


"""iski philosopy bas itni h ki ham ek temprory folder create kr rahe h using save artifact jo as input
PIPELINE, uske metrics , konse data pe train hua , kaha save krna h  ye sab leta h and us path per cuurent utc ke hisab se folder bana deta h jis mai pipeline i.e model.joblib and uska meta data hota h i.e metadata.json and ham uss same per read krte h using hama artifact.py ka function jo model load krne ko responsible h ! load kr ke vo reault ko ham validate krte h with data jo hame save kiya uss location per! """

# Toh poori chain:
# save  →  latest.txt likho ("kaunsa naya")  +  folder/model.joblib + metadata.json
# load  →  latest.txt padho  →  us folder ka model + metadata wapas lao
# test  →  jo save kiya == jo load hua ?  (metrics, features=2, version match)
def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("mental_health.models.save._git_dirty", lambda: False) # Don't ask git
    metrics = {"train": {"r2": 0.98}, "test": {"r2": 0.89}}
    dataset = {"file": "x.csv", "rows": 3, "sha256": "abc"}
    save_artifact(make_fitted_pipe(), metrics, dataset, artifacts_root=tmp_path)

    result = load_latest_artifact(tmp_path)

    assert type(result["pipeline"]).__name__ == "Pipeline"
    assert result["metadata"]["features"]["count"] == 2      # a, b
    assert result["metadata"]["metrics"] == metrics           # metrics metadata ke andar hai
    assert result["version"] == result["metadata"]["model_version"]