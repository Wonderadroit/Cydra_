from pathlib import Path

from cydra.repository_graph import build_repository_graph_records
from cydra.solidity_parser import build_repository_model


def test_repository_graph_records_are_deterministic(tmp_path: Path):
    (tmp_path / "Vault.sol").write_text(
        """
        contract Vault {
            uint256 total;
            function withdraw() external {}
            function deposit() public {}
        }
        """,
        encoding="utf-8",
    )

    model = build_repository_model(tmp_path)
    records = build_repository_graph_records(model)

    assert [r.node_type for r in records] == [
        "contract", "state_variable", "function", "function"
    ]
    assert records[0].attributes["state_variables"] == ["total"]
    assert records[1].attributes["name"] == "total"
    assert records[2].attributes["name"] == "withdraw"
    assert records[3].attributes["name"] == "deposit"
    assert records[2].attributes["contract"] == records[0].node_id
    assert records[1].attributes["contract"] == records[0].node_id
