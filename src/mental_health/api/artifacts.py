
from pathlib import Path
import joblib
import json


# default path for artifacts
DEFAULT_ARTIFACTS_ROOT = Path(__file__).parents[3] / "artifacts"

# Custom Error : so that artifact related Exception & Error can be Identified and thus easy to fix bugs
class ArtifactLoadError(Exception):
    """Raise When Model cannot be loaded for Serving"""

def get_latest_artifact_dir(artifact_root: Path = DEFAULT_ARTIFACTS_ROOT, ):
    """Find the path for the latest Artifact"""

    latest_path = artifact_root / "latest.txt"

    if not latest_path.exists():
        # Raise Error if file latest file not found
        raise ArtifactLoadError(f"Missing Latest file , Path : {latest_path}")

    artifact_version = latest_path.read_text(encoding="utf-8").strip()
    if not artifact_version:
        raise ArtifactLoadError(f"Empty latest artifact pointer: {latest_path}")

    artifact_dir = artifact_root / artifact_version
    if not artifact_dir.is_dir():
        raise ArtifactLoadError(f"Latest artifact directory does not exist: {artifact_dir}")

    return artifact_dir

def load_latest_artifact(artifacts_root: Path = DEFAULT_ARTIFACTS_ROOT) -> dict:
    artifact_dir = get_latest_artifact_dir(artifacts_root)
    model_path = artifact_dir / "model.joblib"
    metadata_path = artifact_dir / "metadata.json"

    if not model_path.exists():
        raise ArtifactLoadError(f"Missing model file: {model_path}")
    if not metadata_path.exists():
        raise ArtifactLoadError(f"Missing metadata file: {metadata_path}")

    pipeline = joblib.load(model_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    return {
        'pipeline':pipeline,
        'metadata':metadata,
        'version':artifact_dir.name,
        'path':artifact_dir,
    }