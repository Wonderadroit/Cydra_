from pathlib import Path

from cydra.repository_graph import project_repository_into_system_model
from cydra.solidity_parser import build_repository_model
from cydra.system_model import SystemModel


def test_repository_projection_adds_contract_state_and_function_nodes(tmp_path: Path):
    (tmp_path / "Vault.sol").write_text(
        """
        contract Vault {
            uint256 total;
            function deposit() external {}
        }
        """,
        encoding="utf-8",
    )
    model = build_repository_model(tmp_path)
    system = SystemModel()

    project_repository_into_system_model(model, system)

    assert "contract:" + str(tmp_path / "Vault.sol") + ":Vault" in system.nodes
    assert any(node.kind == "state_variable" for node in system.nodes.values())
    assert any(node.kind == "function" for node in system.nodes.values())
    assert any(edge.relation == "defined_in" for edge in system.edges)
