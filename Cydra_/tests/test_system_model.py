from cydra.system_model import SystemModel, Node
import hashlib
import json


def test_all_required_kinds():
    model = SystemModel()
    basic_kinds = ["asset", "identity", "trust_boundary", "data_flow", "invariant", "evidence", "hypothesis", "observation", "causal_chain", "belief"]
    for i, kind in enumerate(basic_kinds):
        model.add_node(Node(str(i), kind, kind))
    digest = "execution-request:required-kind"
    model.add_node(Node(f"execution_request:{digest}", "execution_request", "request", _execution_request_attrs(digest)))
    model.add_node(Node(f"execution_result:{digest}", "execution_result", "receipt", _execution_result_attrs(digest)))
    model.add_node(Node("finding", "finding", "finding")); model.add_node(Node("poc", "poc", "poc")); model.add_node(Node("learning", "learning", "learning"))
    assert model.validate() == []


def _execution_request_attrs(digest="execution-request:request-1", execution_id="exec-1"):
    return {"execution_id": execution_id, "adapter": "fake", "target": "fixture", "command": ["fake", "check"], "project_fingerprint": None, "authorization_id": "auth-1", "scope_status": "AUTHORIZED_EXECUTION", "parameters": {}, "digest": digest}


def _execution_result_attrs(digest="execution-request:request-1", execution_id="exec-1"):
    payload = {"execution_id": execution_id, "request_digest": digest, "outcome": "NO_COUNTEREXAMPLE"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {"execution_id": execution_id, "request_digest": digest, "adapter": "fake", "payload": payload, "fingerprint": hashlib.sha256(encoded.encode("utf-8")).hexdigest()}


def test_execution_result_is_a_valid_persistent_kind():
    model = SystemModel(); digest = "execution-request:request-1"
    model.add_node(Node(f"execution_request:{digest}", "execution_request", "request-1", _execution_request_attrs(digest)))
    model.add_node(Node(f"execution_result:{digest}", "execution_result", "receipt", _execution_result_attrs(digest)))
    model.add_node(Node("observation:1", "observation", "observation")); model.connect("observation:1", "executes_request", f"execution_request:{digest}")
    assert model.validate() == [] and model.export()["schema_version"] == "1.22.0"


def test_execution_result_without_canonical_request_is_invalid():
    model = SystemModel(); digest = "execution-request:missing"; model.add_node(Node("execution-result", "execution_result", "receipt", _execution_result_attrs(digest)))
    assert any("not bound to a canonical execution request" in error for error in model.validate())


def test_execution_result_cannot_substitute_request_identity():
    model = SystemModel(); digest = "execution-request:request-1"
    model.add_node(Node(f"execution_request:{digest}", "execution_request", "request-1", _execution_request_attrs(digest, "exec-1")))
    model.add_node(Node(f"execution_result:{digest}", "execution_result", "receipt", _execution_result_attrs(digest, "exec-2")))
    model.add_node(Node("observation:1", "observation", "observation")); model.connect("observation:1", "executes_request", f"execution_request:{digest}")
    assert any("execution identity conflicts" in error for error in model.validate())


def test_duplicate_identical_node_is_idempotent():
    model = SystemModel(); node = Node("asset", "asset", "A", {"sensitivity": "high"}); model.add_node(node); model.add_node(node); assert model.nodes["asset"] == node and len(model.nodes) == 1


def test_duplicate_node_id_with_different_content_is_rejected_without_mutation():
    model = SystemModel(); original = Node("asset", "asset", "A", {"sensitivity": "high"}); model.add_node(original); before = model.export()
    try: model.add_node(Node("asset", "asset", "substituted", {"sensitivity": "critical"}))
    except ValueError as exc: assert "node ID conflicts" in str(exc)
    else: assert False, "canonical node identity substitution must be rejected"
    assert model.export() == before


def test_existing_canonical_node_can_update_attributes_without_identity_substitution():
    model = SystemModel(); original = Node("belief", "belief", "b", {"history": [0.4]}); model.add_node(original); model.update_node_attributes("belief", {"current_confidence": 0.7})
    assert model.nodes["belief"].node_id == original.node_id and model.nodes["belief"].kind == original.kind and model.nodes["belief"].label == original.label
    assert model.nodes["belief"].attributes["history"] == [0.4] and model.nodes["belief"].attributes["current_confidence"] == 0.7


def test_update_missing_canonical_node_fails_without_creation():
    model = SystemModel()
    try: model.update_node_attributes("missing", {"x": 1})
    except KeyError as exc: assert "missing canonical node" in str(exc)
    else: assert False, "attribute update must not create an unvalidated canonical node"
    assert model.nodes == {}


def test_missing_edge_endpoint_is_rejected():
    model = SystemModel(); model.add_node(Node("asset", "asset", "API"))
    try: model.connect("asset", "protects", "missing")
    except KeyError: pass
    else: assert False


def test_reasoning_graph_is_coherent():
    model = SystemModel(); nodes = [Node("asset", "asset", "Protected resource"), Node("identity", "identity", "Requester"), Node("boundary", "trust_boundary", "API boundary"), Node("flow", "data_flow", "Request/response"), Node("invariant", "invariant", "Only authorized identity receives resource"), Node("evidence", "evidence", "Observed response"), Node("hypothesis", "hypothesis", "Authorization invariant violated"), Node("observation", "observation", "Authorized comparison"), Node("cause", "causal_chain", "Authorization failure"), Node("belief", "belief", "Posterior belief")]
    for node in nodes: model.add_node(node)
    model.connect("identity", "crosses", "boundary"); model.connect("identity", "requests", "asset"); model.connect("flow", "carries", "asset"); model.connect("invariant", "constrains", "asset"); model.connect("evidence", "supports", "hypothesis"); model.connect("hypothesis", "tested_by", "observation"); model.connect("observation", "updates", "belief"); model.connect("cause", "explains", "evidence"); model.connect("cause", "supports", "hypothesis")
    assert model.validate() == [] and model.neighbors("hypothesis") == ["observation"]


def test_persistence_round_trip(tmp_path):
    model = SystemModel(); model.add_node(Node("asset", "asset", "A", {"sensitivity": "high"})); model.add_node(Node("identity", "identity", "I")); model.connect("identity", "owns", "asset"); path = tmp_path / "model.json"; model.save(str(path)); loaded = SystemModel.load(str(path)); assert loaded.export() == model.export()


def test_duplicate_edge_is_idempotent():
    model = SystemModel(); model.add_node(Node("asset", "asset", "A")); model.add_node(Node("identity", "identity", "I")); model.connect("identity", "owns", "asset"); model.connect("identity", "owns", "asset"); assert len(model.edges) == 1


def _persisted_finding_attributes():
    return {"persisted": True, "finding_id": "finding-1", "title": "Authorization bypass", "summary": "Unauthorized caller reaches protected state.", "severity": "HIGH", "impact": {"level": "HIGH", "asset_at_risk": "funds", "consequence": "Unauthorized transfer", "prerequisites": ["caller can reach entry point"], "evidence_ids": ["evidence-impact"]}, "affected_components": ["Vault.withdraw"], "evidence_ids": ["evidence-impact"], "hypothesis_id": "hypothesis-1", "poc_reference": "poc-1", "causal_chain_id": "chain-1", "audit_session_id": "session-1", "canonical_evidence_ids": ["evidence-impact"], "canonical_impact_evidence_ids": ["evidence-impact"], "canonical_hypothesis_id": "hypothesis-1", "canonical_causal_chain_id": "chain-1", "canonical_audit_session_id": "session-1"}


def test_persisted_finding_is_semantically_valid_after_export_import():
    model = SystemModel(); model.add_node(Node("finding-1", "finding", "Authorization bypass", _persisted_finding_attributes())); exported = model.export(); loaded = SystemModel.from_dict(exported); assert loaded.export() == exported


def test_rehydration_rejects_tampered_finding_title_label_binding():
    model = SystemModel(); model.add_node(Node("finding-1", "finding", "Authorization bypass", _persisted_finding_attributes())); payload = model.export(); payload["nodes"][0]["attributes"]["title"] = "Substituted claim"
    try: SystemModel.from_dict(payload)
    except ValueError as exc: assert "title conflicts with node label" in str(exc)
    else: assert False, "rehydration must reject substituted finding claims"


def test_rehydration_rejects_tampered_impact_and_severity_binding():
    model = SystemModel(); model.add_node(Node("finding-1", "finding", "Authorization bypass", _persisted_finding_attributes())); payload = model.export(); payload["nodes"][0]["attributes"]["severity"] = "CRITICAL"
    try: SystemModel.from_dict(payload)
    except ValueError as exc: assert "severity does not match impact level" in str(exc)
    else: assert False, "rehydration must reject severity/impact substitution"


def test_rehydration_rejects_substituted_canonical_references():
    model = SystemModel(); model.add_node(Node("finding-1", "finding", "Authorization bypass", _persisted_finding_attributes())); payload = model.export(); payload["nodes"][0]["attributes"]["canonical_hypothesis_id"] = "hypothesis-substituted"
    try: SystemModel.from_dict(payload)
    except ValueError as exc: assert "canonical_hypothesis_id conflicts" in str(exc)
    else: assert False, "rehydration must reject substituted canonical references"
