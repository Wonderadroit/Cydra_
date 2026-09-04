from cydra.audit_session import RepositoryAuditSession
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.system_model import Node, SystemModel


def test_audit_session_does_not_partially_mutate_canonical_on_invalid_ast():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    canonical = SystemModel()
    canonical.add_node(Node("asset:vault", "asset", "Vault"))
    before_nodes = dict(canonical.nodes)
    before_edges = list(canonical.edges)

    try:
        session.scan(
            ["src/app.py", "src/Vault.sol"],
            {"src/app.py": "def run():\n    return 1\n", "src/Vault.sol": "contract Vault {}"},
            {"src/Vault.sol": None},
            canonical,
        )
    except TypeError as exc:
        assert "AST" in str(exc)
    else:
        assert False

    assert canonical.nodes == before_nodes
    assert canonical.edges == before_edges


def test_audit_session_normalizes_duplicate_and_equivalent_paths():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    session = RepositoryAuditSession(policy.decide)
    result = session.scan(
        ["src/./app.py", "src/app.py", "src//app.py"],
        {"src/app.py": "def run():\n    return 1\n"},
    )
    assert result.scanned_paths == ("src/app.py",)
