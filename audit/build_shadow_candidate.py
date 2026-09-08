"""Build a gated min_samples_leaf=5 artifact without moving the primary pointer.

Run from a clean Git checkout:
    uv run --frozen python audit/build_shadow_candidate.py --data-path <csv>
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from mental_health.models.gate import gate
from mental_health.models.save import SavedArtifact, ensure_clean_git_tree, save_artifact
from mental_health.models.train import train


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS_ROOT = ROOT / "runtime" / "shadow-artifacts"
SHADOW_MIN_SAMPLES_LEAF = 5
logger = logging.getLogger(__name__)


def build_shadow_candidate(data_path: Path, artifacts_root: Path) -> SavedArtifact:
    """Train, gate, and publish only to the separate shadow artifact root."""
    data_path = Path(data_path).expanduser().resolve()
    artifacts_root = Path(artifacts_root).expanduser().resolve()
    if not data_path.is_file():
        raise ValueError(f"Data file does not exist: {data_path}")

    # Save enforces this again before publication. Checking before training avoids
    # wasting a full candidate fit when its provenance could not be exact.
    ensure_clean_git_tree()
    pipeline, metrics, dataset = train(
        data_path,
        min_samples_leaf=SHADOW_MIN_SAMPLES_LEAF,
    )
    gate(metrics["cv"])
    return save_artifact(
        pipeline,
        metrics,
        dataset,
        artifacts_root=artifacts_root,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish a gated min_samples_leaf=5 candidate to a shadow-only root."
    )
    parser.add_argument("--data-path", type=Path, required=True)
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=DEFAULT_ARTIFACTS_ROOT,
        help="Separate root for the candidate's latest pointer.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        saved = build_shadow_candidate(args.data_path, args.artifacts_root)
    except Exception as exc:
        logger.error("shadow candidate was not published | %s", exc)
        return 1

    print(
        json.dumps(
            {
                "release_id": saved.version,
                "artifact_dir": str(saved.path),
                "min_samples_leaf": SHADOW_MIN_SAMPLES_LEAF,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
