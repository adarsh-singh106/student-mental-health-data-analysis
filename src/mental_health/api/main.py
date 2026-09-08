from contextlib import asynccontextmanager
import logging
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

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
from mental_health.api.structured_logging import log_unhandled_request_exception


logger = logging.getLogger(__name__)
REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.artifact = load_latest_artifact()
        app.state.startup_error = None
    except ArtifactLoadError as exc:
        app.state.artifact = None
        app.state.startup_error = str(exc)

    app.state.shadow_artifact = None
    app.state.shadow_startup_error = None
    shadow_artifacts_root = os.environ.get("SHADOW_ARTIFACTS_ROOT")
    if shadow_artifacts_root:
        try:
            app.state.shadow_artifact = load_latest_artifact(
                Path(shadow_artifacts_root).expanduser().resolve()
            )
        except ArtifactLoadError as exc:
            app.state.shadow_startup_error = str(exc)
            logger.exception("Shadow artifact is unavailable: %s", exc)

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


@app.middleware("http")
async def assign_request_id(request: Request, call_next):
    """Generate one trusted correlation ID for every normal request lifecycle."""
    request_id = uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.exception_handler(Exception)
def unhandled_exception_handler(req: Request, exc: Exception):
    request_id = getattr(req.state, "request_id", None) or uuid4().hex
    log_unhandled_request_exception(
        request_id=request_id,
        method=req.method,
        path=req.url.path,
        exc=exc,
    )
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


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

    shadow_model_version = None
    shadow_output = None
    shadow_latency_ms = None
    shadow_artifact = req.app.state.shadow_artifact
    if shadow_artifact is not None:
        shadow_started_at = time.perf_counter()
        try:
            shadow_prediction = shadow_artifact["pipeline"].predict(row.copy())
            shadow_output = float(shadow_prediction[0])
            shadow_model_version = shadow_artifact["version"]
            shadow_latency_ms = (time.perf_counter() - shadow_started_at) * 1000
        except Exception:
            logger.exception(
                "Shadow prediction failed | version=%s",
                shadow_artifact["version"],
            )

    prediction_log_path = req.app.state.prediction_log_path
    if prediction_log_path is not None:
        write_prediction(
            prediction_log_path,
            input_payload=input_payload,
            output=score,
            model_version=artifact["version"],
            latency_ms=latency_ms,
            shadow_model_version=shadow_model_version,
            shadow_output=shadow_output,
            shadow_latency_ms=shadow_latency_ms,
        )

    return PredictionResponse(
        mental_health_score=score,
        model_version=artifact["version"],
    )
