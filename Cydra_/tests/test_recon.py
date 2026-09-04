from cydra.recon import NodeKind, RepositoryRecon
from cydra.scope import ScopePolicy, ScopeRule, ScopeState


def test_out_of_scope_nodes_are_not_parsed():
    policy = ScopePolicy([
        ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target"),
        ScopeRule("tests/**", ScopeState.OUT_OF_SCOPE, "excluded test code"),
    ])
    recon = RepositoryRecon(policy.decide)
    model = recon.scan(
        ["src/app.py", "tests/test_app.py"],
        {
            "src/app.py": "def main():\n    return 1\n",
            "tests/test_app.py": "def should_not_be_parsed():\n    return 2\n",
        },
    )

    assert any(n.path == "tests/test_app.py" and n.scope is ScopeState.OUT_OF_SCOPE for n in model.nodes)
    assert not any(n.path == "tests/test_app.py" and n.kind is NodeKind.FUNCTION for n in model.nodes)


def test_recon_initializes_python_structure():
    policy = ScopePolicy([ScopeRule("src/**", ScopeState.IN_SCOPE, "audit target")])
    recon = RepositoryRecon(policy.decide)
    model = recon.scan(
        ["src/api.py"],
        {"src/api.py": "from auth import authorize\n\ndef api_get():\n    authorize()\n"},
    )

    kinds = {n.kind for n in model.nodes}
    assert NodeKind.MODULE in kinds
    assert NodeKind.FUNCTION in kinds
    assert NodeKind.ENTRY_POINT in kinds
    assert NodeKind.IMPORT in kinds
    assert NodeKind.AUTHORIZATION in kinds


def test_unknown_scope_is_preserved_and_not_active():
    policy = ScopePolicy([])
    recon = RepositoryRecon(policy.decide)
    model = recon.scan(["unknown/app.py"], {"unknown/app.py": "def run():\n    pass\n"})

    assert model.nodes[0].scope is ScopeState.UNKNOWN
    assert model.active_nodes() == []
