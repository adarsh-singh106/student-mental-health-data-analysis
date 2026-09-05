
from mental_health.data.preparation import prepare_data
from mental_health.features.preprocessing import build_preprocessor
from mental_health.models.gate import gate
from mental_health.models.save import save_artifact

from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor

from sklearn.metrics import root_mean_squared_error,mean_absolute_error,r2_score

import hashlib

from pathlib import Path
import logging
logger = logging.getLogger(__name__)


# Helper Function to compute metrics
def _compute_metrics(y_true,y_pred):
    mae = mean_absolute_error(y_true,y_pred)
    rmse = root_mean_squared_error(y_true,y_pred)
    r2 = r2_score(y_true,y_pred)
    
    return {
        "mae":mae,
        "rmse":rmse,
        "r2":r2
    }

def train(path:Path):
    logger.info("training started | data=%s", path)

    # Get prepared DF from data preparation Pipeline
    prepared_df = prepare_data(path)

    # Make Dataset dict for adding in metadata
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    dataset = {
        "file":path.name,
        "rows":len(prepared_df),
        "sha256":sha
    }

    # Split Features & Target Column
    X = prepared_df.drop(columns=['Mental_Health_Score'])
    y = prepared_df['Mental_Health_Score']

    # Three-way split: train 60 / val 20 / test 20.
    # Done in two steps because train_test_split only cuts in two:
    #   step 1 -> hold out 20% as the final TEST set (locked in a vault,
    #             touched exactly once at the very end).
    #   step 2 -> cut the remaining 80% into train (75% of 80% = 60% of all)
    #             and validation (25% of 80% = 20% of all).
    # We SELECT and GATE on validation; test only reports the final honest number.
    X_temp, X_test, y_temp, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_temp, y_temp, test_size=0.25, random_state=42
    )

    pipeline = Pipeline([
        ("prep",build_preprocessor()),
        ("model",RandomForestRegressor(random_state=42,n_jobs=1))
    ])

    pipeline.fit(X_train,y_train)

    # Training Metrics (how well it fit what it has already seen)
    y_pred_train = pipeline.predict(X_train)
    train_metrics = _compute_metrics(y_train,y_pred_train)

    # Validation Metrics (unseen by the model; what we select/gate on)
    y_pred_val = pipeline.predict(X_val)
    val_metrics = _compute_metrics(y_val,y_pred_val)

    # Test Metrics (the vault — computed once, only reported)
    y_pred_test = pipeline.predict(X_test)
    test_metrics = _compute_metrics(y_test,y_pred_test)

    return pipeline, {
        "train":train_metrics,
        "val":val_metrics,
        "test":test_metrics
    },dataset


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    path = Path(__file__).parents[3] / "data" / "raw" / "Student Social Media And Mental Health Impact.csv"
    pipeline, metrics, dataset = train(path)

    # 1. TRAIN
    train_metrics = metrics["train"]
    val_metrics = metrics["val"]
    test_metrics = metrics["test"]

    logger.info("train | r2=%.4f mae=%.4f rmse=%.4f", train_metrics["r2"], train_metrics["mae"], train_metrics["rmse"])
    logger.info("val   | r2=%.4f mae=%.4f rmse=%.4f", val_metrics["r2"], val_metrics["mae"], val_metrics["rmse"])
    logger.info("test  | r2=%.4f mae=%.4f rmse=%.4f", test_metrics["r2"], test_metrics["mae"], test_metrics["rmse"])

    # 2. GATE (raise / save)
    gate(metrics)
    logger.info("gate passed")

    # 3. SAVE (Only if passed through GATE)
    save_artifact(pipeline, metrics, dataset)
    logger.info("artifact Saved")