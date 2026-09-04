from pathlib import Path

from cydra.benchmark_verifier import verify_ast_relationship_observation
from cydra.planner import Observation
from cydra.updater import EvidencePolarity


def _ast():
    return {
        "nodeType": "SourceUnit",
        "nodes": [
            {
                "nodeType": "ContractDefinition",
                "id": 1,
                "name": "AddPairLogic",
                "nodes": [
                    {
                        "nodeType": "VariableDeclaration",
                        "id": 10,
                        "name": "uniswapPool",
                        "stateVariable": False,
                        "typeDescriptions": {"typeIdentifier": "t_contract$_IUniswapV3Pool_$"},
                    },
                    {
                        "nodeType": "FunctionDefinition",
                        "id": 16071,
                        "name": "addPair",
                        "scope": 1,
                        "body": {
                            "nodeType": "Block",
                            "statements": [
                                {
                                    "nodeType": "FunctionCall",
                                    "id": 31,
                                    "src": "16071:20:0",
                                    "expression": {
                                        "nodeType": "MemberAccess",
                                        "id": 30,
                                        "memberName": "fee",
                                        "expression": {
                                            "nodeType": "Identifier",
                                            "id": 29,
                                            "name": "uniswapPool",
                                            "referencedDeclaration": 10,
                                            "typeDescriptions": {"typeIdentifier": "t_contract$_IUniswapV3Pool_$"},
                                        },
                                    },
                                    "arguments": [],
                                }
                            ],
                        },
                    },
                ],
            }
        ],
    }


def _observation(target: str = "AddPairLogic.uniswapPool.fee") -> Observation:
    return Observation(
        "verify:function:AddPairLogic.addPair:16071:external_call:data_flow:src/libraries/logic/AddPairLogic.sol:" + target,
        ["CONFIRMED", "REFUTED"],
        1.0,
        authorized=True,
    )


def test_ast_verifier_confirms_exact_compiler_relationship(tmp_path: Path):
    source = tmp_path / "src/libraries/logic/AddPairLogic.sol"
    source.parent.mkdir(parents=True)
    source.write_text("library AddPairLogic {}\n", encoding="utf-8")

    result = verify_ast_relationship_observation(
        _observation(),
        tmp_path,
        {"src/libraries/logic/AddPairLogic.sol": _ast()},
    )

    assert result.outcome == "CONFIRMED"
    assert result.evidence_polarity == {
        "relationship:function:AddPairLogic.addPair:16071:external_call:data_flow:src/libraries/logic/AddPairLogic.sol:AddPairLogic.uniswapPool.fee": EvidencePolarity.SUPPORTS,
    }
    assert result.details["matches"] == 1
    assert result.details["verifier"] == "solc-ast-relationship"


def test_ast_verifier_refutes_absent_relationship(tmp_path: Path):
    source = tmp_path / "src/libraries/logic/AddPairLogic.sol"
    source.parent.mkdir(parents=True)
    source.write_text("library AddPairLogic {}\n", encoding="utf-8")

    result = verify_ast_relationship_observation(
        _observation("AddPairLogic.uniswapPool.token0"),
        tmp_path,
        {"src/libraries/logic/AddPairLogic.sol": _ast()},
    )

    assert result.outcome == "REFUTED"
    assert result.evidence_polarity[
        "relationship:function:AddPairLogic.addPair:16071:external_call:data_flow:src/libraries/logic/AddPairLogic.sol:AddPairLogic.uniswapPool.token0"
    ] == EvidencePolarity.CONTRADICTS
