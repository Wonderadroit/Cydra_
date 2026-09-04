#!/usr/bin/env python3
"""Run CYDRA against one materialized historical case without its oracle."""
from __future__ import annotations

import argparse
from pathlib import Path
import shlex

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import (
    MaterializedBenchmarkInput,
    validate_materialized_input,
)
from cydra.benchmark_run import run_blind_command


def _load_entry(path: Path) -> BenchmarkCorpusEntry:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    return BenchmarkCorpusEntry(
        case_id=data["case_id"],
        contest_name=data["contest_name"],
        repository=data["repository"],
        revision=data["revision"],
        input_paths=tuple(data["input_paths"]),
        excluded_paths=tuple(data.get("excluded_paths", ())),
    )


def _load_receipt(path: Path) -> MaterializedBenchmarkInput:
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    return MaterializedBenchmarkInput(
        case_id=data["case_id"],
        corpus_fingerprint=data["corpus_fingerprint"],
        repository=data["repository"],
        revision=data["revision"],
        selected_paths=tuple(data["selected_paths"]),
        file_manifest=tuple((item["path"], item["sha256"]) for item in data["file_manifest"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runner-revision", required=True)
    parser.add_argument("--command", required=True, help="Quoted CYDRA command executed from the blind staging directory")
    args = parser.parse_args()

    case = _load_entry(args.manifest)
    receipt_path = args.staging / ".cydra-blind-receipt.json"
    materialized = _load_receipt(receipt_path)
    validate_materialized_input(case, args.staging, materialized)

    receipt = run_blind_command(
        case,
        materialized,
        args.staging,
        command=tuple(shlex.split(args.command)),
        runner_revision=args.runner_revision,
        candidate_output=args.output,
    )
    receipt_path = args.staging / ".cydra-blind-run-receipt.json"
    receipt_path.write_text(receipt.to_json(), encoding="utf-8")

    print(f"case_id={receipt.case_id}")
    print(f"runner_revision={receipt.runner_revision}")
    print(f"candidate_output_sha256={receipt.candidate_output_sha256}")
    print(f"run_fingerprint={receipt.fingerprint()}")
    print(f"candidate_output={args.output.resolve()}")
    print(f"run_receipt={receipt_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
