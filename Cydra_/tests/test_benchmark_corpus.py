import pytest

from cydra.benchmark_corpus import (
    BenchmarkCorpusEntry,
    BenchmarkCorpusError,
    validate_corpus,
)


SHA = "a" * 40


def make_entry(**overrides):
    values = {
        "case_id": "predy-2024-05",
        "contest_name": "historical-predy",
        "repository": "code-423n4/2024-05-predy",
        "revision": SHA,
        "input_paths": ("README.md", "src/"),
        "excluded_paths": ("4naly3er-report.md", "reports/"),
    }
    values.update(overrides)
    return BenchmarkCorpusEntry(**values)


def test_corpus_entry_is_blind_and_deterministically_fingerprinted():
    entry = make_entry()
    assert entry.fingerprint()
    assert not hasattr(entry, "oracle")
    assert not hasattr(entry, "findings")
    assert not hasattr(entry, "known_issues")


def test_report_artifact_cannot_enter_blind_input():
    with pytest.raises(BenchmarkCorpusError):
        make_entry(input_paths=("README.md", "4naly3er-report.md"))


def test_selected_path_must_be_frozen_in_manifest():
    entry = make_entry()
    entry.validate_selected_paths(("README.md", "src/"))
    with pytest.raises(BenchmarkCorpusError):
        entry.validate_selected_paths(("README.md", "scope.txt"))


def test_excluded_path_fails_closed_even_if_selected():
    entry = make_entry()
    with pytest.raises(BenchmarkCorpusError):
        entry.validate_selected_paths(("4naly3er-report.md",))


def test_invalid_revision_is_rejected():
    with pytest.raises(BenchmarkCorpusError):
        make_entry(revision="main")


def test_duplicate_paths_and_case_ids_are_rejected():
    with pytest.raises(BenchmarkCorpusError):
        make_entry(input_paths=("README.md", "README.md"))
    with pytest.raises(BenchmarkCorpusError):
        validate_corpus((make_entry(), make_entry()))


def test_corpus_validation_is_oracle_free():
    entries = validate_corpus((make_entry(),))
    assert len(entries) == 1
    assert entries[0].case_id == "predy-2024-05"
