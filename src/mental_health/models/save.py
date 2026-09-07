"""Publish a fitted model as an immutable, self-verifying artifact directory."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import pandas
import sklearn
from sklearn.pipeline import Pipeline

from mental_health.data.schema import TARGET_COLUMN
from mental_health.models.artifact_contract import (
    ARTIFACT_CONTRACT_VERSION,
    MANIFEST_FILENAME,
    METADATA_FILENAME,
    MODEL_FILENAME,
    describe_file,
    sha256_file,
)
from mental_health.models.gate import MAX_CV_MAE


DEFAULT_REPOSITORY_ROOT = Path(__file__).parents[3]
DEFAULT_ARTIFACTS_ROOT = DEFAULT_REPOSITORY_ROOT / "artifacts"


class DirtyTreeError(Exception):
    """Raised when a release would not have an exact source-code revision."""


class SourceControlError(RuntimeError):
    """Raised when Git provenance cannot be recorded for a host-side release."""


class ArtifactPublicationError(ValueError):
    """Raised when a caller has not supplied the required artifact contract data."""


@dataclass(frozen=True)
class SavedArtifact:
    """Locations and identity returned after an artifact is fully published."""

    version: str
    path: Path
    manifest_path: Path


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=DEFAULT_REPOSITORY_ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise SourceControlError(
            "Unable to record Git provenance. Run releases from a Git checkout with Git installed."
        ) from exc


def _git_commit() -> str:
    return _git_output("rev-parse", "HEAD")


def _git_dirty() -> bool:
    return bool(_git_output("status", "--porcelain"))


def ensure_clean_git_tree() -> None:
    """Fail before an expensive training run if provenance cannot be exact."""
    if _git_dirty():
        raise DirtyTreeError("Refusing to publish a model from a dirty Git working tree.")
    # Also verify Git can resolve a commit now, before training consumes time.
    _git_commit()


def _release_version(now: datetime) -> str:
    """Create a sortable, collision-resistant immutable release identifier."""
    return f"{now.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _publish_latest(artifacts_root: Path, version: str) -> None:
    """Atomically move the mutable pointer only after the release is complete."""
    latest_path = artifacts_root / "latest.txt"
    temporary_path = artifacts_root / f".latest-{uuid4().hex}.tmp"
    # Preserve the pre-existing pointer format exactly: just the release id.
    temporary_path.write_text(version, encoding="utf-8")
    temporary_path.replace(latest_path)


def save_artifact(
    artifact_pipeline: Pipeline,
    metrics: dict,
    dataset: dict,
    artifacts_root: Path | None = None,
) -> SavedArtifact:
    """Write and publish an artifact only after all release files are complete.

    The release folder is constructed in a private staging directory. It becomes
    visible to consumers only after the model, metadata, and manifest are all
    present; ``latest.txt`` moves last. This prevents a server from selecting a
    half-written release after a failed write or interrupted process.
    """
    ensure_clean_git_tree()

    artifacts_root = Path(artifacts_root or DEFAULT_ARTIFACTS_ROOT).resolve()
    artifacts_root.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    version = _release_version(now)
    created_at = now.isoformat()
    final_dir = artifacts_root / version
    staging_dir = Path(tempfile.mkdtemp(prefix=".staging-", dir=artifacts_root))
    schema_version = dataset.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        shutil.rmtree(staging_dir)
        raise ArtifactPublicationError("Dataset metadata must include a feature schema version.")

    try:
        model_path = staging_dir / MODEL_FILENAME
        metadata_path = staging_dir / METADATA_FILENAME
        manifest_path = staging_dir / MANIFEST_FILENAME

        joblib.dump(artifact_pipeline, model_path)
        feature_names = artifact_pipeline.named_steps["prep"].get_feature_names_out().tolist()
        model_file = describe_file(model_path)

        metadata = {
            "model_version": version,
            "created_at_utc": created_at,
            "artifact": {
                "contract_version": ARTIFACT_CONTRACT_VERSION,
                "model_sha256": model_file["sha256"],
            },
            "features": {
                "count": len(feature_names),
                "names": feature_names,
                "schema_version": schema_version,
            },
            "target": TARGET_COLUMN,
            "model": {
                "name": type(artifact_pipeline.named_steps["model"]).__name__,
                "params": artifact_pipeline.named_steps["model"].get_params(),
            },
            "metrics": metrics,
            "gate": {
                "passed": True,
                "thresholds": {"max_cv_mae": MAX_CV_MAE},
            },
            "git": {"commit": _git_commit(), "dirty": False},
            "dataset": dataset,
            "env": {
                "python": platform.python_version(),
                "sklearn": sklearn.__version__,
                "pandas": pandas.__version__,
                "uv_lock_sha256": sha256_file(DEFAULT_REPOSITORY_ROOT / "uv.lock"),
            },
        }
        _write_json(metadata_path, metadata)

        manifest = {
            "contract_version": ARTIFACT_CONTRACT_VERSION,
            "release_id": version,
            "created_at_utc": created_at,
            "files": {
                MODEL_FILENAME: model_file,
                METADATA_FILENAME: describe_file(metadata_path),
            },
        }
        _write_json(manifest_path, manifest)

        # A directory rename on the same filesystem makes the completed release
        # appear as one unit; consumers never select the staging directory.
        staging_dir.replace(final_dir)
        _publish_latest(artifacts_root, version)
    except Exception:
        # This directory was created by tempfile directly under artifacts_root.
        # Remove only that known staging path; never touch prior releases.
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    return SavedArtifact(
        version=version,
        path=final_dir,
        manifest_path=final_dir / MANIFEST_FILENAME,
    )
