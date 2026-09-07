"""Create one auditable model release from an explicit input dataset."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Sequence

from mental_health.models.gate import GateFailedError, gate
from mental_health.models.save import (
    DirtyTreeError,
    SavedArtifact,
    SourceControlError,
    ensure_clean_git_tree,
    save_artifact,
)
from mental_health.models.train import train


logger = logging.getLogger(__name__)


class ReleaseInputError(ValueError):
    """Raised when a release command is given an unusable input path."""


def release(data_path: Path, artifacts_root: Path) -> SavedArtifact:
    """Run train -> gate -> publish using paths supplied by the caller.

    Keeping this orchestration outside ``train.py`` makes the release boundary
    explicit: a caller must name both the source data and where the immutable
    artifact will be published.
    """
    data_path = Path(data_path).expanduser().resolve()
    artifacts_root = Path(artifacts_root).expanduser().resolve()

    if not data_path.is_file():
        raise ReleaseInputError(f"Data file does not exist: {data_path}")

    logger.info("release started | data=%s artifacts_root=%s", data_path, artifacts_root)
    ensure_clean_git_tree()
    pipeline, metrics, dataset = train(data_path)
    logger.info(
        "cv metrics | r2=%.4f +/- %.4f mae=%.4f +/- %.4f",
        metrics["cv"]["r2_mean"],
        metrics["cv"]["r2_std"],
        metrics["cv"]["mae_mean"],
        metrics["cv"]["mae_std"],
    )
    gate(metrics["cv"])

    saved = save_artifact(
        pipeline,
        metrics,
        dataset,
        artifacts_root=artifacts_root,
    )
    logger.info("release published | version=%s path=%s", saved.version, saved.path)
    return saved


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train, gate, and publish one auditable model artifact."
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        required=True,
        help="CSV used for this release. Its SHA-256 is recorded in metadata.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
        help="Directory that receives immutable release folders (default: artifacts).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Application log level (default: INFO).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level))

    try:
        saved = release(args.data_path, args.artifacts_root)
    except ReleaseInputError as exc:
        logger.error("release rejected | %s", exc)
        return 2
    except (DirtyTreeError, SourceControlError, GateFailedError) as exc:
        logger.error("release failed | %s", exc)
        return 1

    print(
        json.dumps(
            {
                "release_id": saved.version,
                "artifact_dir": str(saved.path),
                "manifest": str(saved.manifest_path),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
