import json
from pathlib import Path

from cydra.benchmark_corpus import BenchmarkCorpusEntry


MANIFEST = Path("data/benchmarks/immunefi-arbitration-boost-2024-03.json")


def test_first_immunefi_manifest_is_oracle_free_and_pinned():
    raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = BenchmarkCorpusEntry(
        case_id=raw["case_id"],
        contest_name=raw["contest_name"],
        repository=raw["repository"],
        revision=raw["revision"],
        input_paths=tuple(raw["input_paths"]),
        excluded_paths=tuple(raw["excluded_paths"]),
    )
    assert entry.revision == "49c1de26cda19c9e8a4aa311ba3b0dc864f34a25"
    assert not hasattr(entry, "oracle")
    assert not any("report" in p.lower() for p in entry.input_paths)
    assert "src/" in entry.input_paths
