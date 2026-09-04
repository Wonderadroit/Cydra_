from pathlib import Path

from cydra.repository_graph import project_repository_into_system_model
from cydra.solidity_parser import build_repository_model
from cydra.system_model import SystemModel


def test_repository_model_projects_into_persistent_system_model(tmp_path: Path):
    (tmp_path / "Vault.sol").write_text(
        "contract Vault { uint256 total; function withdraw() external {} }",
        encoding="utf-8",
    )

    repository = build_repository_model(tmp_path)
    system = SystemModel()
    project_repository_into_system_model(repository, system)

    contract_id = f"contract:{tmp_path / 'Vault.sol'}:Vault"
    function_id = f"function:{tmp_path / 'Vault.sol'}:1:Vault:withdraw"
    assert system.nodes[contract_id].kind == "contract"
    assert system.nodes[function_id].kind == "function"
    assert system.neighbors(function_id, "defined_in") == [contract_id]
    assert system.validate() == []

    # Projection is idempotent for the same repository model.
    project_repository_into_system_model(repository, system)
    assert len(system.nodes) == 2
    assert len(system.edges) == 1
