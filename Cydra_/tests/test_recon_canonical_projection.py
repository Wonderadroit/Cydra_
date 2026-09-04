from cydra.graph_semantics import validate_graph
from cydra.recon import NodeKind, RepositoryRecon
from cydra.scope import ScopePolicy, ScopeRule, ScopeState
from cydra.system_model import SystemModel


def test_recon_projects_into_canonical_system_model():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target")])
    recon = RepositoryRecon(policy.decide)
    snapshot = recon.scan(
        ["src/api.py"],
        {"src/api.py": "from auth import authorize\n\ndef api_get():\n    authorize()\n"},
    )

    canonical = recon.to_canonical(snapshot)
    assert isinstance(canonical, SystemModel)
    assert canonical.nodes["file:src/api.py"].kind == "file"
    assert canonical.nodes["module:src/api.py"].kind == "module"
    assert canonical.nodes["function:src/api.py:3:api_get"].kind == "function"
    assert canonical.nodes["entry:src/api.py:3:api_get"].kind == "entry_point"
    assert canonical.nodes["import:src/api.py:1:authorize"].kind == "import"
    assert canonical.nodes["authorization:src/api.py:4:authorize"].kind == "authorization"
    assert canonical.nodes["file:src/api.py"].attributes["scope_state"] == "IN_SCOPE"
    assert validate_graph(canonical) == []


def test_recon_canonical_projection_preserves_out_of_scope_without_parsing():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE),
        ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE),
    ])
    recon = RepositoryRecon(policy.decide)
    canonical = recon.scan_canonical(
        ["src/app.py", "tests/test_app.py"],
        {
            "src/app.py": "def run():\n    return 1\n",
            "tests/test_app.py": "def should_not_parse():\n    return 2\n",
        },
    )

    assert canonical.nodes["file:tests/test_app.py"].attributes["scope_state"] == "OUT_OF_SCOPE"
    assert "module:tests/test_app.py" not in canonical.nodes
    assert not any(node.kind == NodeKind.FUNCTION.value and node.attributes.get("path") == "tests/test_app.py" for node in canonical.nodes.values())
    assert validate_graph(canonical) == []


def test_recon_projection_does_not_infer_security_claims():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE)])
    recon = RepositoryRecon(policy.decide)
    canonical = recon.scan_canonical(["src/auth.py"], {"src/auth.py": "def require_auth():\n    pass\n"})

    assert all(node.kind not in {"hypothesis", "invariant", "finding"} for node in canonical.nodes.values())
