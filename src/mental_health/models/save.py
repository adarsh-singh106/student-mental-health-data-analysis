from datetime import datetime,timezone
from sklearn.pipeline import Pipeline
from pathlib import Path
import joblib
import json
import subprocess

import sklearn, pandas, platform

from mental_health.models.gate import MIN_TEST_R2,MAX_TEST_MAE,MAX_TEST_RMSE

def _git_commit():
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()

def _git_dirty():
    out = subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    )
    return out.strip() != ""

def make_dir(fname:str, artifacts_root:str):
    folder = artifacts_root / fname

    folder.mkdir(parents=True)
    return folder

def save_artifact(artifact_pipeline:Pipeline, metrics:dict, dataset:dict, artifacts_root: Path = None):
    # When default artifact is not provided
    if artifacts_root is None: # Better practice to use "is"
        artifacts_root = Path(__file__).parents[3] / "artifacts"
        # artifacts_root --> Now the artifacts_root itself is a ROOT Path ! 

    now = datetime.now(timezone.utc)
    dir_name = now.strftime("%Y%m%dT%H%M%SZ")
    created_at = now.isoformat()

    folder = make_dir(dir_name,artifacts_root)

    joblib.dump(artifact_pipeline,folder / "model.joblib")
    names = artifact_pipeline.named_steps["prep"].get_feature_names_out().tolist()
    metadata = {
        "model_version":dir_name,
        "created_at_utc":created_at,
        "features":{
            "count":len(names),
            "names":names
        },
        "target":"Mental_Health_Score",
        "model":{
            "name":type(artifact_pipeline.named_steps["model"]).__name__ ,
            "params":artifact_pipeline.named_steps["model"].get_params(),
        },
        "metrics": metrics,
        "gate":{
            "passed":True,
            "thresholds": {
        "min_test_r2": MIN_TEST_R2,
        "max_test_mae": MAX_TEST_MAE,
        "max_test_rmse": MAX_TEST_RMSE
            }
        },
        "git": {"commit": _git_commit(), "dirty": _git_dirty()},
        "dataset": dataset,
        "env": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "pandas": pandas.__version__,
        },

    }

    with open(folder / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    
    latest = artifacts_root / "latest.txt"
    latest.write_text(dir_name)

    