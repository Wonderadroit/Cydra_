from cydra.audit_session import RepositoryAuditSession
from cydra.graph_semantics import validate_graph
from cydra.scope import ScopePolicy, ScopeRule, ScopeState


AST = {
    "nodeType": "SourceUnit",
    "nodes": [{
        "nodeType": "ContractDefinition",
        "id": 1,
        "name": "Vault",
        "nodes": [
            {"nodeType": "VariableDeclaration", "id": 10, "name": "balance", "stateVariable": True, "scope": 1},
            {"nodeType": "FunctionDefinition", "id": 20, "name": "deposit", "scope": 1,
             "body": {"nodeType": "Block", "statements": [{
                 "nodeType": "Assignment", "operator": "+=",
                 "leftHandSide": {"nodeType": "Identifier", "id": 30, "name": "balance",
                                  "referencedDeclaration": 10, "src": "110:7:0"},
                 "rightHandSide": {"nodeType": "Literal", "value": "1"},
             }]}}
        ],
    }]
}


def test_audit_session_composes_python_and_solidity_into_one_canonical_model():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target"),
        ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "tests excluded"),
    ])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(
        ["src/app.py", "src/Vault.sol", "tests/test_app.py"],
        {
            "src/app.py": "def run():\n    return 1\n",
            "src/Vault.sol": "contract Vault {}\n",
            "tests/test_app.py": "def should_not_parse():\n    return 2\n",
        },
        {"src/Vault.sol": AST},
    )

    assert result.scanned_paths == ("src/app.py", "src/Vault.sol", "tests/test_app.py")
    assert result.solidity_paths == ("src/Vault.sol",)
    assert result.out_of_scope_paths == ("tests/test_app.py",)
    assert result.model.nodes["function:Vault.deposit:20"].kind == "function"
    assert result.model.nodes["state_variable:Vault.balance:10"].kind == "state_variable"
    assert "module:tests/test_app.py" not in result.model.nodes
    assert result.model.nodes[result.session_id].kind == "audit_session"
    assert result.model.neighbors(result.session_id, "contains") == ["file:src/Vault.sol", "file:src/app.py", "file:tests/test_app.py"]
    assert all(node.kind not in {"hypothesis", "invariant", "finding"} for node in result.model.nodes.values())
    assert validate_graph(result.model) == []


def test_audit_session_fails_closed_when_source_is_missing():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    try:
        session.scan(["src/Vault.sol"], {}, {"src/Vault.sol": AST})
    except KeyError as exc:
        assert "source missing" in str(exc)
    else:
        assert False


def test_audit_session_does_not_parse_solidity_without_ast_artifact():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(["src/Vault.sol"], {"src/Vault.sol": "contract Vault {}"})

    assert result.solidity_paths == ()
    assert "file:src/Vault.sol" in result.model.nodes
    assert result.model.nodes[result.session_id].kind == "audit_session"
    assert validate_graph(result.model) == []


def test_audit_session_provenance_is_self_verifying():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(
        ["src/a.py", "src/Vault.sol"],
        {"src/a.py": "print('a')", "src/Vault.sol": "contract Vault {}"},
        {"src/Vault.sol": AST},
    )

    assert RepositoryAuditSession.validate_persisted_provenance(result.model, result.session_id) == []


def test_audit_session_provenance_detects_intake_fingerprint_tampering():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(["src/a.py"], {"src/a.py": "print('a')"})
    result.model.nodes[result.session_id].attributes["intake_id"] = "intake:tampered"

    errors = RepositoryAuditSession.validate_persisted_provenance(result.model, result.session_id)
    assert "intake_id does not match persisted provenance" in errors


def test_audit_session_provenance_detects_manifest_tampering():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(["src/a.py"], {"src/a.py": "print('a')"})
    result.model.nodes[result.session_id].attributes["source_manifest"][0]["sha256"] = "0" * 64

    errors = RepositoryAuditSession.validate_persisted_provenance(result.model, result.session_id)
    assert "intake_id does not match persisted provenance" in errors


def test_audit_session_provenance_detects_missing_file_node():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(["src/a.py"], {"src/a.py": "print('a')"})
    del result.model.nodes["file:src/a.py"]

    errors = RepositoryAuditSession.validate_persisted_provenance(result.model, result.session_id)
    assert "scanned path missing canonical file node: file:src/a.py" in errors
