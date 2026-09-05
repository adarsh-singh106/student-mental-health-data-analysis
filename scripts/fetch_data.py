"""Verify (do NOT auto-download) the raw dataset for this project.

Why this script does not download anything:
    The source repo carries **no license** (see data/PROVENANCE.md), so reuse
    terms are undefined and this project does not fetch or redistribute the CSV
    programmatically. Instead this script gives a cloner a concrete, checkable
    path to a working data/raw/:

      - file present  -> hash it, compare against the known-good sha256, exit 0/1
      - file missing  -> print exactly where to get it and where to put it, exit 2

Usage:
    python scripts/fetch_data.py

Exit codes:
    0  file present and sha256 matches
    1  file present but sha256 does NOT match (corrupt / wrong file)
    2  file missing (instructions printed)
"""

import hashlib
import sys
from pathlib import Path

# --- Provenance facts -------------------------------------------------------
# Expected hash is a fixed, known-good value: the whole point of an integrity
# check is that the expected hash comes from a source SEPARATE from the file
# being checked. If you ever change the dataset, update BOTH this constant and
# data/PROVENANCE.md together so they never drift apart.
EXPECTED_FILENAME = "Student Social Media And Mental Health Impact.csv"
EXPECTED_SHA256 = "32b542a497c39389735710fb4e2f43bdf444af5d9bacde6289801d201b6bebd3"
SOURCE_URL = (
    "https://github.com/tanishq-latent/Mental-Health-Score/blob/main/"
    "Student%20Social%20Media%20And%20Mental%20Health%20Impact.csv"
)

# data/raw/<file>, resolved relative to the repo root (this file is in scripts/)
REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
CSV_PATH = RAW_DIR / EXPECTED_FILENAME


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _print_manual_step() -> None:
    print(
        f"""
Dataset not found at:
    {CSV_PATH}

This project does NOT auto-download the file: the source repo has no license,
so its reuse terms are undefined and it is not redistributed here (see
data/PROVENANCE.md).

To place it manually:
  1. Download the CSV from:
       {SOURCE_URL}
  2. Save it as exactly:
       {EXPECTED_FILENAME}
     into:
       {RAW_DIR}
  3. Re-run this script to verify the sha256.
""".strip()
    )


def main() -> int:
    if not CSV_PATH.exists():
        _print_manual_step()
        return 2

    actual = _sha256(CSV_PATH)
    if actual == EXPECTED_SHA256:
        print(f"OK  {CSV_PATH.name}")
        print(f"    sha256 {actual} matches PROVENANCE.md")
        return 0

    print(f"FAIL  {CSV_PATH.name}")
    print(f"    expected sha256 {EXPECTED_SHA256}")
    print(f"    actual   sha256 {actual}")
    print("    The file on disk is not the one this project was fingerprinted against.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
