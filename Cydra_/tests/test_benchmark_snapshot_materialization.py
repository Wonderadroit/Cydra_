import hashlib
from pathlib import Path

import pytest

from cydra.benchmark_corpus import BenchmarkCorpusEntry
from cydra.benchmark_materialization import BenchmarkMaterializationError, materialize_blind_snapshot


REV = "49c1de26cda19c9e8a4aa311ba3b0dc864f34a25"


def _blob_sha(content: bytes) -> str:
    return hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()


def _entry() -> BenchmarkCorpusEntry:
    return BenchmarkCorpusEntry(
        case_id="snapshot-test",
        contest_name="snapshot",
        repository="immunefi-team/vaults",
        revision=REV,
        input_paths=("README.md", "src/"),
        excluded_paths=("reports/", "findings/"),
    )


def test_connector_snapshot_verifies_git_blob_identity(tmp_path: Path) -> None:
    readme = b"# exact\n"
    source = b"pragma solidity 0.8.18;\ncontract A {}\n"
    receipt = materialize_blind_snapshot(
        _entry(),
        "immunefi-team/vaults",
        REV,
        (("README.md", _blob_sha(readme), readme), ("src/A.sol", _blob_sha(source), source)),
        tmp_path / "staging",
    )
    assert receipt.revision == REV
    assert (tmp_path / "staging/src/A.sol").read_bytes() == source


def test_connector_snapshot_rejects_content_mismatch(tmp_path: Path) -> None:
    source = b"pragma solidity 0.8.18;\n"
    with pytest.raises(BenchmarkMaterializationError, match="Git blob mismatch"):
        materialize_blind_snapshot(
            _entry(),
            "immunefi-team/vaults",
            REV,
            (("src/A.sol", "0" * 40, source),),
            tmp_path / "staging",
        )


def test_connector_snapshot_rejects_wrong_revision(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkMaterializationError, match="revision"):
        materialize_blind_snapshot(
            _entry(),
            "immunefi-team/vaults",
            "0" * 40,
            (("README.md", _blob_sha(b"# exact\n"), b"# exact\n"),),
            tmp_path / "staging",
        )
