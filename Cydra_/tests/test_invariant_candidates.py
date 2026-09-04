from cydra.ast_dataflow import SemanticRelationshipEvidence
from cydra.invariants import InvariantCandidate, candidates_from_system_model
from cydra.system_model import SystemModel


def test_only_evidence_backed_edges_become_candidates():
    model = SystemModel()
    evidence = SemanticRelationshipEvidence(
        contract="Vault", function="deposit", relation="writes", target="balance",
        confidence=0.95, source="solc-json-ast:Vault.sol", ast_node_id=30,
        source_location=(110, 7, 0),
    )
    model.project_ast_evidence([evidence])
    candidates = candidates_from_system_model(model)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert isinstance(candidate, InvariantCandidate)
    assert candidate.confidence == 0.95
    assert candidate.evidence_count == 1
    assert candidate.source_ids == ("solc-json-ast:Vault.sol:30",)
    assert "writes" in candidate.statement
    assert "balance" in candidate.statement


def test_unbacked_graph_edges_do_not_become_invariant_candidates():
    model = SystemModel()
    model.add_node(__import__("cydra.system_model", fromlist=["Node"]).Node("function:Vault:deposit", "function", "deposit"))
    model.add_node(__import__("cydra.system_model", fromlist=["Node"]).Node("state_variable:Vault:balance", "state_variable", "balance"))
    model.connect("function:Vault:deposit", "writes", "state_variable:Vault:balance")

    assert candidates_from_system_model(model) == ()


def test_precondition_becomes_a_system_derived_invariant_candidate():
    from cydra.system_model import Node
    model = SystemModel()
    model.add_node(Node("function:Vault.withdraw:20", "function", "withdraw"))
    model.add_node(Node("data_flow:Vault.sol:amount_gt_zero", "data_flow", "(amount > 0)", {"evidence_backed": True, "candidate": True}))
    model.connect(
        "function:Vault.withdraw:20", "precondition", "data_flow:Vault.sol:amount_gt_zero",
        confidence=0.98, provenance="solc-json-ast:Vault.sol", ast_node_id=40,
        evidence_backed=True, candidate=True,
    )
    candidates = candidates_from_system_model(model)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.statement == "successful execution of withdraw requires (amount > 0)"
    assert candidate.metadata["category"] == "precondition"
    assert candidate.metadata["relation"] == "precondition"


def test_transition_obligation_combines_precondition_and_state_write():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault.withdraw:20", "function", "withdraw"))
    model.add_node(Node("data_flow:Vault.sol:amount_gt_zero", "data_flow", "(amount > 0)", {"evidence_backed": True, "candidate": True}))
    model.add_node(Node("state_variable:Vault.balance:10", "state_variable", "balance"))
    model.connect(
        "function:Vault.withdraw:20", "precondition", "data_flow:Vault.sol:amount_gt_zero",
        confidence=0.98, provenance="solc-json-ast:Vault.sol", ast_node_id=40,
        evidence_backed=True, candidate=True,
    )
    model.connect(
        "function:Vault.withdraw:20", "writes", "state_variable:Vault.balance:10",
        confidence=0.95, provenance="solc-json-ast:Vault.sol", ast_node_id=50,
        evidence_backed=True, candidate=True,
    )

    candidates = candidates_from_system_model(model)
    transitions = [c for c in candidates if c.metadata.get("category") == "transition_obligation"]

    assert len(transitions) == 1
    candidate = transitions[0]
    assert candidate.statement == "successful execution of withdraw requires (amount > 0) before changing balance"
    assert candidate.evidence_count == 2
    assert candidate.confidence == 0.95
    assert candidate.metadata["written_state"] == "state_variable:Vault.balance:10"


def test_state_dependency_transition_combines_distinct_read_and_write_states():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault:deposit:20", "function", "deposit"))
    model.add_node(Node("state_variable:Vault:totalAssets:10", "state_variable", "totalAssets"))
    model.add_node(Node("state_variable:Vault:totalShares:11", "state_variable", "totalShares"))
    model.connect(
        "function:Vault:deposit:20", "reads", "state_variable:Vault:totalAssets:10",
        confidence=0.95, provenance="solc-json-ast:Vault.sol", ast_node_id=41,
        evidence_backed=True, candidate=True,
    )
    model.connect(
        "function:Vault:deposit:20", "writes", "state_variable:Vault:totalShares:11",
        confidence=0.95, provenance="solc-json-ast:Vault.sol", ast_node_id=42,
        evidence_backed=True, candidate=True,
    )

    candidates = candidates_from_system_model(model)
    dependencies = [c for c in candidates if c.metadata.get("category") == "state_dependency_transition"]

    assert len(dependencies) == 1
    candidate = dependencies[0]
    assert candidate.statement == "execution of deposit changes totalShares using information read from totalAssets"
    assert candidate.evidence_count == 2
    assert candidate.metadata["read_state"] == "state_variable:Vault:totalAssets:10"
    assert candidate.metadata["written_state"] == "state_variable:Vault:totalShares:11"


def test_transition_expression_becomes_a_system_derived_invariant_candidate():
    from cydra.invariants import candidates_from_system_model
    from cydra.system_model import SystemModel

    model = SystemModel()
    model.add_ast_evidence(SemanticRelationshipEvidence(
        contract="Vault", function="deposit", relation="transition_expression",
        target="totalShares", confidence=0.98, source="solc-json-ast:Vault.sol",
        ast_node_id=30, function_ast_node_id=20, target_ast_node_id=10,
        metadata={
            "operation": "=",
            "expression": "totalShares = (totalShares + totalAssets)",
            "rhs_expression": "(totalShares + totalAssets)",
            "dependency_ids": [10, 11],
            "dependency_labels": ["totalShares", "totalAssets"],
        },
    ))
    candidates = candidates_from_system_model(model)
    matches = [c for c in candidates if c.metadata.get("category") == "state_transition_expression"]
    assert len(matches) == 1
    assert matches[0].statement == "execution of deposit updates totalShares using totalShares = (totalShares + totalAssets)"
    assert matches[0].metadata["dependency_ids"] == [10, 11]


def test_cross_function_updates_create_shared_state_consistency_candidate():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault:deposit:20", "function", "deposit"))
    model.add_node(Node("function:Vault:withdraw:21", "function", "withdraw"))
    model.add_node(Node("state_variable:Vault:totalShares:10", "state_variable", "totalShares"))
    for function_id, ast_id, expression in (
        ("function:Vault:deposit:20", 31, "totalShares + mintedShares"),
        ("function:Vault:withdraw:21", 41, "totalShares - burnedShares"),
    ):
        model.connect(
            function_id, "transition_expression", "state_variable:Vault:totalShares:10",
            confidence=0.98, provenance="solc-json-ast:Vault.sol", ast_node_id=ast_id,
            evidence_backed=True, candidate=True, operation="=", expression=expression,
        )

    candidates = candidates_from_system_model(model)
    matches = [c for c in candidates if c.metadata.get("category") == "cross_function_state_consistency"]

    assert len(matches) == 1
    candidate = matches[0]
    assert candidate.statement == (
        "updates to shared state totalShares across 2 functions must preserve a coherent state relationship"
    )
    assert candidate.evidence_count == 2
    assert candidate.confidence == 0.98
    assert candidate.metadata["shared_state"] == "state_variable:Vault:totalShares:10"
    assert candidate.metadata["function_ids"] == ["function:Vault:deposit:20", "function:Vault:withdraw:21"]
    assert candidate.metadata["transition_ast_node_ids"] == [31, 41]


def test_single_function_state_transition_does_not_create_cross_function_candidate():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault:deposit:20", "function", "deposit"))
    model.add_node(Node("state_variable:Vault:totalShares:10", "state_variable", "totalShares"))
    model.connect(
        "function:Vault:deposit:20", "transition_expression", "state_variable:Vault:totalShares:10",
        confidence=0.98, provenance="solc-json-ast:Vault.sol", ast_node_id=31,
        evidence_backed=True, candidate=True, operation="=", expression="totalShares + mintedShares",
    )

    candidates = candidates_from_system_model(model)
    assert not [c for c in candidates if c.metadata.get("category") == "cross_function_state_consistency"]


def test_cross_function_shared_dependency_creates_specific_transition_coupling_candidate():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault:deposit:20", "function", "deposit"))
    model.add_node(Node("function:Vault:withdraw:21", "function", "withdraw"))
    model.add_node(Node("state_variable:Vault:totalShares:10", "state_variable", "totalShares", {"ast_node_id": 10}))
    model.add_node(Node("state_variable:Vault:totalAssets:11", "state_variable", "totalAssets", {"ast_node_id": 11}))
    for function_id, ast_id, expression in (
        ("function:Vault:deposit:20", 31, "totalShares + totalAssets"),
        ("function:Vault:withdraw:21", 41, "totalShares - totalAssets"),
    ):
        model.connect(
            function_id, "transition_expression", "state_variable:Vault:totalShares:10",
            confidence=0.98, provenance="solc-json-ast:Vault.sol", ast_node_id=ast_id,
            evidence_backed=True, candidate=True, operation="=", expression=expression,
            dependency_ids=[10, 11],
        )

    candidates = candidates_from_system_model(model)
    matches = [c for c in candidates if c.metadata.get("category") == "cross_function_transition_coupling"]

    assert len(matches) == 1
    assets = [c for c in matches if c.metadata["dependency_state"] == "state_variable:Vault:totalAssets:11"]
    assert len(assets) == 1
    candidate = assets[0]
    assert candidate.statement == (
        "updates to shared state totalShares across 2 functions depend on totalAssets; "
        "investigate whether those transitions preserve the same relationship between totalShares and totalAssets"
    )
    assert candidate.source_ids == (
        "solc-json-ast:Vault.sol:31",
        "solc-json-ast:Vault.sol:41",
    )
    assert candidate.metadata["function_ids"] == ["function:Vault:deposit:20", "function:Vault:withdraw:21"]
    assert candidate.metadata["common_dependency_ast_node_id"] == 11


def test_cross_function_transition_coupling_requires_common_dependency():
    from cydra.system_model import Node

    model = SystemModel()
    model.add_node(Node("function:Vault:a:20", "function", "a"))
    model.add_node(Node("function:Vault:b:21", "function", "b"))
    model.add_node(Node("state_variable:Vault:shared:10", "state_variable", "shared", {"ast_node_id": 10}))
    model.add_node(Node("state_variable:Vault:x:11", "state_variable", "x", {"ast_node_id": 11}))
    model.add_node(Node("state_variable:Vault:y:12", "state_variable", "y", {"ast_node_id": 12}))
    model.connect(
        "function:Vault:a:20", "transition_expression", "state_variable:Vault:shared:10",
        confidence=0.9, provenance="solc-json-ast:A.sol", ast_node_id=30,
        evidence_backed=True, candidate=True, operation="=", expression="shared + x", dependency_ids=[10, 11],
    )
    model.connect(
        "function:Vault:b:21", "transition_expression", "state_variable:Vault:shared:10",
        confidence=0.9, provenance="solc-json-ast:B.sol", ast_node_id=40,
        evidence_backed=True, candidate=True, operation="=", expression="shared + y", dependency_ids=[10, 12],
    )

    candidates = candidates_from_system_model(model)
    assert not [c for c in candidates if c.metadata.get("category") == "cross_function_transition_coupling"]
