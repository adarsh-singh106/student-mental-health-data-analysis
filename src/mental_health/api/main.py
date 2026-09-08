from contextlib import asynccontextmanager
import logging
import sqlite3
import time

import pandas as pd
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from mental_health.api.artifacts import ArtifactLoadError, load_latest_artifact
from mental_health.api.prediction_log import (
    initialize_prediction_log,
    resolve_prediction_log_path,
    write_prediction,
)
from mental_health.api.schemas import PredictionRequest, PredictionResponse


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.artifact = load_latest_artifact()
        app.state.startup_error = None
    except ArtifactLoadError as exc:
        app.state.artifact = None
        app.state.startup_error = str(exc)

    try:
        prediction_log_path = resolve_prediction_log_path()
        initialize_prediction_log(prediction_log_path)
        app.state.prediction_log_path = prediction_log_path
    except (OSError, sqlite3.Error) as exc:
        app.state.prediction_log_path = None
        logger.exception("Prediction logging is unavailable: %s", exc)
    yield

app = FastAPI(
    title="Student Mental Health Prediction API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(Exception)
def unhandled_exception_handler(req: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# GET /healthz: is the application process running?
@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# GET /readyz: is the model available to serve predictions?
@app.get("/readyz")
def readyz(req: Request):
    artifact = req.app.state.artifact

    if artifact is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": req.app.state.startup_error,
            },
        )

    return {
        "status": "ready",
        "model_version": artifact["version"],
    }


# POST /predict: run the loaded model on one validated request.
@app.post("/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest, req: Request) -> PredictionResponse | JSONResponse:
    artifact = req.app.state.artifact

    if artifact is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": req.app.state.startup_error,
            },
        )
    input_payload = payload.model_dump(mode="json")
    started_at = time.perf_counter()
    row = pd.DataFrame([input_payload])
    prediction = artifact["pipeline"].predict(row)
    score = float(prediction[0])
    latency_ms = (time.perf_counter() - started_at) * 1000

    prediction_log_path = req.app.state.prediction_log_path
    if prediction_log_path is not None:
        write_prediction(
            prediction_log_path,
            input_payload=input_payload,
            output=score,
            model_version=artifact["version"],
            latency_ms=latency_ms,
        )

    return PredictionResponse(
        mental_health_score=score,
        model_version=artifact["version"],
    )
