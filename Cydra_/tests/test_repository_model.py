from pathlib import Path

from cydra.repository_model import discover_source_files


def test_source_discovery_is_deterministic(tmp_path: Path):
    (tmp_path / "z.sol").write_text("contract Z {}", encoding="utf-8")
    (tmp_path / "a.sol").write_text("contract A {}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    assert [p.name for p in discover_source_files(tmp_path)] == ["a.sol", "z.sol"]


def test_missing_repository_is_explicit(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    try:
        discover_source_files(missing)
    except FileNotFoundError as exc:
        assert exc.args[0] == missing
    else:
        raise AssertionError("missing repository must fail explicitly")
