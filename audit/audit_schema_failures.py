"""Deliberately break temporary CSV copies and record their failure boundary.

Run from the repository root:
    uv run --frozen python audit/audit_schema_failures.py

The source CSV is never modified. The report describes where each malformed copy
was rejected before it could reach training or sklearn transformation.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

from mental_health.data.preparation import prepare_data
from mental_health.data.schema import DataContractError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = ROOT / "data" / "raw" / "Student Social Media And Mental Health Impact.csv"
DEFAULT_REPORT_PATH = ROOT / "audit" / "REPORT_schema_failures.md"
OUT: list[str] = []


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def compact(value: object, limit: int = 300) -> str:
    return " ".join(str(value).split())[:limit]


def describe_failure(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, DataContractError):
        return (
            "structural column contract",
            "DataContractError before cleaning",
            compact(exc),
        )

    if isinstance(exc, pa.errors.SchemaErrors):
        cases = exc.failure_cases.head(3).to_dict(orient="records")
        return (
            "Pandera dataframe validation",
            f"SchemaErrors with {len(exc.failure_cases)} failure case(s) after cleaning",
            compact(json.dumps(cases, default=str)),
        )

    if isinstance(exc, pa.errors.SchemaError):
        return (
            "Pandera dataframe validation",
            "SchemaError after cleaning",
            compact(exc),
        )

    return (
        "unexpected boundary",
        type(exc).__name__,
        compact(exc),
    )


def run_case(name: str, description: str, path: Path) -> None:
    try:
        prepare_data(path)
    except Exception as exc:
        layer, exception_type, detail = describe_failure(exc)
        say(f"### {name}")
        say()
        say(f"- Mutation: {description}")
        say(f"- Rejected at: **{layer}**")
        say(f"- Exception: `{exception_type}`")
        say(f"- Evidence: `{detail}`")
        say("- sklearn training/transform/prediction reached: **no**")
        say()
    else:
        say(f"### {name}")
        say()
        say(f"- Mutation: {description}")
        say("- Result: **unexpectedly accepted**")
        say("- sklearn training/transform/prediction reached: not tested after acceptance")
        say()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run schema-breakage experiments against temporary CSV copies."
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=DEFAULT_DATA_PATH,
        help="Known-good source CSV. It is read but never modified.",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Markdown evidence path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    data_path = args.data_path.expanduser().resolve()
    report_path = args.report_path.expanduser().resolve()
    if not data_path.is_file():
        raise SystemExit(f"CSV does not exist: {data_path}")

    original = pd.read_csv(data_path)
    say("# Schema-breakage audit")
    say()
    say(f"- Source CSV: `{data_path}`")
    say("- The source file was read once and was not modified.")
    say(f"- Baseline shape: **{original.shape[0]} rows x {original.shape[1]} columns**")
    say()

    try:
        prepared = prepare_data(data_path)
    except Exception as exc:
        raise SystemExit(f"Known-good source CSV failed validation: {exc}") from exc
    else:
        say(f"- Baseline prepare_data result: **accepted ({prepared.shape[0]} rows x "
            f"{prepared.shape[1]} columns)**")
        say()

    cases: list[tuple[str, str, Callable[[pd.DataFrame], pd.DataFrame]]] = [
        (
            "Unexpected column",
            "Added `Audit_Unexpected_Column`; production schemas often receive this "
            "after an upstream export adds a field.",
            lambda df: df.assign(Audit_Unexpected_Column="unexpected"),
        ),
        (
            "Missing cleaning dependency",
            "Deleted `Physical_Activity_Hours`; the cleaning step normally indexes "
            "this exact column.",
            lambda df: df.drop(columns=["Physical_Activity_Hours"]),
        ),
        (
            "Non-numeric Age",
            "Replaced one Age value with `not-an-integer`, forcing CSV parsing to "
            "produce a non-coercible value rather than a harmless numeric string.",
            lambda df: df.assign(Age=df["Age"].astype(object).mask(df.index == df.index[0], "not-an-integer")),
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="mental-health-schema-audit-") as temp_dir:
        temp_root = Path(temp_dir)
        for index, (name, description, mutate) in enumerate(cases, start=1):
            broken_path = temp_root / f"case-{index}.csv"
            mutate(original.copy()).to_csv(broken_path, index=False)
            run_case(name, description, broken_path)

    say("## Summary")
    say()
    say("| Mutation | Expected boundary | Why it matters |")
    say("|---|---|---|")
    say("| Extra column | Structural contract before cleaning | Rejects schema drift explicitly instead of silently ignoring a field. |")
    say("| Missing `Physical_Activity_Hours` | Structural contract before cleaning | Prevents a later cleaning `KeyError` that obscures the data-contract cause. |")
    say("| Non-numeric `Age` | Pandera validation after cleaning | Catches semantic type corruption before sklearn receives the frame. |")
    say()
    say("These experiments call `prepare_data()` only. A successful schema boundary "
        "does not prove downstream model quality; it proves malformed CSVs are "
        "stopped before the training pipeline can use them.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print(f"\n>>> wrote {report_path}")


if __name__ == "__main__":
    main()
