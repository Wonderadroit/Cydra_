from cydra.audit_session import RepositoryAuditSession
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.system_model import SystemModel
from tests.test_audit_session import AST


def session():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE),
        ScopeRule("tests/**", ScopeState.IN_SCOPE),
    ])
    return RepositoryAuditSession(policy.decide)


def test_session_persists_provenance_manifest_in_canonical_graph():
    audit = session()
    result = audit.scan(["src/app.py"], {"src/app.py": "def run():\n    return 1\n"})
    node = result.model.nodes[result.session_id]
    assert node.kind == "audit_session"
    assert node.attributes["intake_id"] == result.intake_id
    assert node.attributes["passive"] is True
    assert result.source_manifest[0][0] == "src/app.py"
    assert len(result.source_manifest[0][1]) == 64
    assert result.scope_decisions == (("src/app.py", "IN_SCOPE"),)
    assert result.model.validate() == []


def test_equivalent_intake_is_deterministic_within_one_session():
    audit = session()
    first = audit.scan(["src/./app.py", "src/app.py"], {"src/app.py": "return 1"})
    second = audit.scan(["src/app.py", "src//app.py"], {"src/app.py": "return 1"})
    assert first.scanned_paths == second.scanned_paths == ("src/app.py",)
    assert first.intake_id == second.intake_id
    assert first.source_manifest == second.source_manifest
    assert first.session_id == second.session_id


def test_distinct_sessions_have_distinct_identity_but_same_intake_fingerprint():
    first = session().scan(["src/app.py"], {"src/app.py": "return 1"})
    second = session().scan(["src/app.py"], {"src/app.py": "return 1"})
    assert first.session_id != second.session_id
    assert first.intake_id == second.intake_id


def test_scope_and_artifact_manifests_are_explicit_without_security_inference():
    audit = session()
    result = audit.scan(
        ["src/Vault.sol", "tests/Vault.t.sol"],
        {"src/Vault.sol": "contract Vault {}", "tests/Vault.t.sol": "contract VaultTest {}"},
        {"src/Vault.sol": AST},
    )
    assert result.out_of_scope_paths == ()
    assert result.solidity_paths == ("src/Vault.sol",)
    assert result.scope_decisions == (("src/Vault.sol", "IN_SCOPE"), ("tests/Vault.t.sol", "IN_SCOPE"))
    assert result.solidity_artifact_manifest[0][0] == "src/Vault.sol"
    assert len(result.solidity_artifact_manifest[0][1]) == 64
    session_node = result.model.nodes[result.session_id]
    assert "hypothesis" not in session_node.attributes
    assert "finding" not in session_node.attributes


def test_audit_session_does_not_mutate_supplied_model_before_success():
    audit = session()
    canonical = SystemModel()
    before = canonical.export()
    try:
        audit.scan(
            ["src/app.py", "src/Vault.sol"],
            {"src/app.py": "x", "src/Vault.sol": "contract Vault {}"},
            {"src/Vault.sol": None},
            canonical,
        )
    except TypeError:
        pass
    else:
        assert False
    assert canonical.export() == before
