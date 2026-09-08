"""Shared on-disk contract for a published model artifact.

The trainer writes this contract and the serving process verifies it before
deserializing a model.  It detects accidental corruption; it is not a
cryptographic signature or a substitute for trusted artifact storage.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


ARTIFACT_CONTRACT_VERSION = 1
MODEL_FILENAME = "model.joblib"
METADATA_FILENAME = "metadata.json"
MANIFEST_FILENAME = "manifest.json"


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest without loading a potentially large file at once."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_file(path: Path) -> dict[str, int | str]:
    """Return the immutable facts a manifest records for one artifact file."""
    return {
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }
