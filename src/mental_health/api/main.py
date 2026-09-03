from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from mental_health.api.artifacts import ArtifactLoadError, load_latest_artifact
from mental_health.api.schemas import PredictionRequest, PredictionResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.artifact = load_latest_artifact()
        app.state.startup_error = None
    except ArtifactLoadError as exc:
        app.state.artifact = None
        app.state.startup_error = str(exc)
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
    row = pd.DataFrame([payload.model_dump()])
    prediction = artifact["pipeline"].predict(row)

    return PredictionResponse(
        mental_health_score=float(prediction[0]),
        model_version=artifact["version"],
    )