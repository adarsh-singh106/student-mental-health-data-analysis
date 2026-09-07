"""Locate and verify model artifacts before they are deserialized for serving."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import pandas
import sklearn

from mental_health.models.artifact_contract import (
    ARTIFACT_CONTRACT_VERSION,
    MANIFEST_FILENAME,
    METADATA_FILENAME,
    MODEL_FILENAME,
    describe_file,
)
from mental_health.data.schema import FEATURE_SCHEMA_VERSION


logger = logging.getLogger(__name__)
DEFAULT_ARTIFACTS_ROOT = Path(__file__).parents[3] / "artifacts"


class ArtifactLoadError(Exception):
    """Raised when an artifact cannot safely be selected or loaded for serving."""


def _read_json(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactLoadError(f"Cannot read {description}: {path.name}") from exc
    if not isinstance(value, dict):
        raise ArtifactLoadError(f"Invalid {description}: {path.name}")
    return value


def get_latest_artifact_dir(artifact_root: Path = DEFAULT_ARTIFACTS_ROOT) -> Path:
    """Return the latest artifact directory without allowing pointer traversal."""
    artifact_root = Path(artifact_root).resolve()
    latest_path = artifact_root / "latest.txt"

    if not latest_path.exists():
        raise ArtifactLoadError("Missing latest artifact pointer.")

    try:
        artifact_version = latest_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ArtifactLoadError("Cannot read latest artifact pointer.") from exc

    if not artifact_version:
        raise ArtifactLoadError("Latest artifact pointer is empty.")
    if Path(artifact_version).name != artifact_version:
        raise ArtifactLoadError("Latest artifact pointer contains an invalid release id.")

    artifact_dir = (artifact_root / artifact_version).resolve()
    try:
        artifact_dir.relative_to(artifact_root)
    except ValueError as exc:
        raise ArtifactLoadError("Latest artifact pointer escapes the artifact root.") from exc

    if not artifact_dir.is_dir():
        raise ArtifactLoadError("Latest artifact directory does not exist.")
    return artifact_dir


def _verify_manifest(artifact_dir: Path, version: str) -> tuple[dict | None, bool]:
    """Verify new-contract artifacts before ``joblib.load`` touches their model."""
    manifest_path = artifact_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        # Existing local artifacts predate the contract. They remain loadable so
        # the migration does not strand a working demo, but are visibly not a
        # verified release. New artifacts always include a manifest.
        logger.warning("Loading legacy artifact without a manifest | version=%s", version)
        return None, False

    manifest = _read_json(manifest_path, "artifact manifest")
    if manifest.get("contract_version") != ARTIFACT_CONTRACT_VERSION:
        raise ArtifactLoadError("Artifact manifest has an unsupported contract version.")
    if manifest.get("release_id") != version:
        raise ArtifactLoadError("Artifact manifest release id does not match its directory.")

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ArtifactLoadError("Artifact manifest has no file inventory.")

    for filename in (MODEL_FILENAME, METADATA_FILENAME):
        expected = files.get(filename)
        path = artifact_dir / filename
        if not isinstance(expected, dict):
            raise ArtifactLoadError(f"Artifact manifest has no record for {filename}.")
        if not path.is_file():
            raise ArtifactLoadError(f"Missing artifact file: {filename}")

        actual = describe_file(path)
        if actual != expected:
            raise ArtifactLoadError(f"Artifact integrity check failed for {filename}.")

    return manifest, True


def _verify_runtime_compatibility(metadata: dict) -> None:
    """Fail closed when a verified artifact was built with different core libraries."""
    environment = metadata.get("env")
    if not isinstance(environment, dict):
        raise ArtifactLoadError("Verified artifact has no environment metadata.")

    expected_versions = {
        "sklearn": sklearn.__version__,
        "pandas": pandas.__version__,
    }
    for name, installed in expected_versions.items():
        expected = environment.get(name)
        if expected != installed:
            raise ArtifactLoadError(
                f"Artifact requires {name} {expected!r}; server has {installed!r}."
            )

    features = metadata.get("features")
    if not isinstance(features, dict):
        raise ArtifactLoadError("Verified artifact has no feature metadata.")
    if features.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise ArtifactLoadError(
            "Artifact feature schema does not match the serving application's schema."
        )


def load_latest_artifact(artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT) -> dict:
    """Load the selected artifact after checking layout, integrity, and compatibility."""
    artifact_dir = get_latest_artifact_dir(artifacts_root)
    version = artifact_dir.name
    model_path = artifact_dir / MODEL_FILENAME
    metadata_path = artifact_dir / METADATA_FILENAME

    if not model_path.exists():
        raise ArtifactLoadError(f"Missing model file: {MODEL_FILENAME}")
    if not metadata_path.exists():
        raise ArtifactLoadError(f"Missing metadata file: {METADATA_FILENAME}")

    manifest, integrity_verified = _verify_manifest(artifact_dir, version)
    metadata = _read_json(metadata_path, "artifact metadata")

    if metadata.get("model_version") != version:
        raise ArtifactLoadError("Artifact metadata model version does not match its directory.")

    if integrity_verified:
        _verify_runtime_compatibility(metadata)
        artifact_metadata = metadata.get("artifact")
        if not isinstance(artifact_metadata, dict):
            raise ArtifactLoadError("Verified artifact has no artifact metadata.")
        if artifact_metadata.get("contract_version") != ARTIFACT_CONTRACT_VERSION:
            raise ArtifactLoadError("Artifact metadata has an unsupported contract version.")
        if artifact_metadata.get("model_sha256") != manifest["files"][MODEL_FILENAME]["sha256"]:
            raise ArtifactLoadError("Artifact metadata model checksum does not match manifest.")

    try:
        pipeline = joblib.load(model_path)
    except Exception as exc:
        raise ArtifactLoadError("Unable to deserialize model artifact.") from exc

    return {
        "pipeline": pipeline,
        "metadata": metadata,
        "version": version,
        "path": artifact_dir,
        "manifest": manifest,
        "integrity_verified": integrity_verified,
    }
