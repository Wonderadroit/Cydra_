import pytest

from cydra.system_model import Edge, Node, SystemModel


def _model():
    model = SystemModel()
    model.add_node(Node("observation:a", "observation", "a"))
    model.add_node(Node("observation:b", "observation", "b"))
    model.add_node(Node("execution_request:r", "execution_request", "r", {
        "execution_id": "exec-1",
        "adapter": "foundry",
        "target": "fixture",
        "command": ["forge", "test"],
        "project_fingerprint": None,
        "authorization_id": "auth-1",
        "scope_status": "AUTHORIZED_EXECUTION",
        "digest": "execution-request:r",
    }))
    return model


def test_execution_request_cannot_bind_to_two_observations():
    model = _model()
    model.add_edge(Edge("observation:a", "executes_request", "execution_request:r"))
    with pytest.raises(ValueError, match="already bound"):
        model.add_edge(Edge("observation:b", "executes_request", "execution_request:r"))
    assert model.neighbors("observation:a", "executes_request") == ["execution_request:r"]
    assert model.neighbors("observation:b", "executes_request") == []


def test_execution_request_binding_rejects_wrong_endpoint_kinds():
    model = _model()
    with pytest.raises(ValueError, match="must connect"):
        model.add_edge(Edge("execution_request:r", "executes_request", "observation:a"))


def test_deserialized_ambiguous_execution_binding_fails_closed():
    model = _model()
    payload = model.export()
    payload["edges"] = [
        {"source": "observation:a", "relation": "executes_request", "target": "execution_request:r", "attributes": {}},
        {"source": "observation:b", "relation": "executes_request", "target": "execution_request:r", "attributes": {}},
    ]
    with pytest.raises(ValueError, match="already bound"):
        SystemModel.from_dict(payload)
