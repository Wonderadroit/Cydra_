from pathlib import Path

from cydra.solidity_parser import build_repository_model, parse_solidity_file


def test_parser_extracts_contract_functions_and_visibility(tmp_path: Path):
    source = tmp_path / "Vault.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Vault {
            mapping(address => uint256) public balance;
            function deposit() external payable { balance[msg.sender] += msg.value; }
            function withdraw(uint256 amount) external { balance[msg.sender] -= amount; }
        }
        """,
        encoding="utf-8",
    )

    contracts = parse_solidity_file(source)
    assert len(contracts) == 1
    assert contracts[0].name == "Vault"
    assert contracts[0].state_variables == ("balance",)
    assert [(f.name, f.visibility) for f in contracts[0].functions] == [
        ("deposit", "external"),
        ("withdraw", "external"),
    ]


def test_repository_model_is_built_from_source_inventory(tmp_path: Path):
    (tmp_path / "A.sol").write_text("contract A { function ping() public {} }", encoding="utf-8")
    (tmp_path / "B.sol").write_text("contract B { function pong() external {} }", encoding="utf-8")

    model = build_repository_model(tmp_path)
    assert [c.name for c in model.contracts] == ["A", "B"]
    assert len(model.files) == 2
