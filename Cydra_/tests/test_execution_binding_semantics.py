from cydra.graph_semantics import validate_graph
from cydra.system_model import Edge, Node, SystemModel


def test_execution_request_binding_is_a_known_graph_relation():
    model = SystemModel()
    model.add_node(Node("observation:o", "observation", "o"))
    model.add_node(Node("execution_request:r", "execution_request", "r", {
        "execution_id": "exec-1",
        "adapter": "fake",
        "target": "fixture",
        "command": ["fake", "check"],
        "project_fingerprint": None,
        "authorization_id": "auth-1",
        "scope_status": "AUTHORIZED_EXECUTION",
        "digest": "execution-request:r",
    }))
    model.add_edge(Edge("observation:o", "executes_request", "execution_request:r"))
    assert validate_graph(model) == []
