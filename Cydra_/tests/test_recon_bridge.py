from cydra.recon_bridge import scan_into_system_model
from cydra.scope import ScopeDecision, ScopeState


def resolver(path):
    return ScopeDecision(path, ScopeState.IN_SCOPE, True, "test scope")


def test_passive_recon_populates_canonical_system_model():
    model = scan_into_system_model(
        ["app.py"],
        {"app.py": "def run():\n    return 1\n"},
        resolver,
    )
    assert "file:app.py" in model.nodes
    assert "module:app.py" in model.nodes
    assert any(node.kind == "function" and node.label == "run" for node in model.nodes.values())
    assert model.validate() == []


def test_out_of_scope_file_is_retained_but_not_parsed():
    def resolver(path):
        return ScopeDecision(path, ScopeState.OUT_OF_SCOPE, False, "excluded")

    model = scan_into_system_model(["secret.py"], {"secret.py": "def run(): pass"}, resolver)
    assert "file:secret.py" in model.nodes
    assert "module:secret.py" not in model.nodes
    assert model.nodes["file:secret.py"].attributes["scope"] == "OUT_OF_SCOPE"
