from pathlib import Path

from cydra.semantic_model import derive_semantic_model
from cydra.solidity_parser import build_repository_model


def test_semantic_model_preserves_uncertainty(tmp_path: Path):
    source = tmp_path / "Vault.sol"
    source.write_text(
        """
        contract Vault {
            uint256 total;
            function withdraw() external onlyOwner {}
        }
        """,
        encoding="utf-8",
    )

    structural = build_repository_model(tmp_path)
    semantic = derive_semantic_model(structural)

    function = semantic.contracts[0].functions[0]
    assert function.name == "withdraw"
    assert function.visibility == "external"
    assert function.modifiers == ("onlyOwner",)
    # Structural parsing alone must not invent a state read/write relationship.
    assert function.state_candidates == ()
