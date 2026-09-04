#!/usr/bin/env python3
"""Materialize one frozen historical benchmark without exposing its oracle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import materialize_blind_input, validate_materialized_input


def _load_entry(path: Path) -> BenchmarkCorpusEntry:
    data = json.loads(path.read_text(encoding="utf-8"))
    return BenchmarkCorpusEntry(
        case_id=data["case_id"],
        contest_name=data["contest_name"],
        repository=data["repository"],
        revision=data["revision"],
        input_paths=tuple(data["input_paths"]),
        excluded_paths=tuple(data.get("excluded_paths", ())),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    entry = _load_entry(args.manifest)
    receipt = materialize_blind_input(entry, args.source, args.destination)
    # Revalidate the staged snapshot immediately at the CLI boundary. The object
    # returned by materialization is the only provenance receipt handed forward.
    validate_materialized_input(entry, args.destination, receipt)

    print(f"case_id={receipt.case_id}")
    print(f"corpus_fingerprint={receipt.corpus_fingerprint}")
    print(f"revision={receipt.revision}")
    print(f"files={len(receipt.selected_paths)}")
    print(f"snapshot_fingerprint={receipt.fingerprint()}")
    print(f"staging={args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
