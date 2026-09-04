import hashlib
import json

import pytest

from cydra.reasoning_graph import ReasoningGraph
from cydra.security_reasoning import emit_verified_security_claims, persist_verified_security_claim

from test_security_claim_emission import (
    add_verified_causal_chain,
    add_verified_update,
    prepared_graph,
)


def _audit_digest(event):
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _rehash_history(payload):
    previous_hash = ReasoningGraph.AUDIT_GENESIS
    for sequence, event in enumerate(payload["history"]):
        event["sequence"] = sequence
        event["previous_hash"] = previous_hash
        event["event_hash"] = _audit_digest(event)
        previous_hash = event["event_hash"]


def _verified_claim_state():
    graph, inputs = prepared_graph()
    _, outcome_id, belief_id = add_verified_update(graph, inputs)
    add_verified_causal_chain(graph, inputs, outcome_id, belief_id)
    claim = emit_verified_security_claims(graph, inputs)[0]
    persist_verified_security_claim(graph, claim)
    return graph


def test_reloaded_graph_rejects_replayed_state_with_missing_security_claim_event():
    graph = _verified_claim_state()
    payload = graph.export_state()
    payload["history"] = [
        event
        for event in payload["history"]
        if event.get("type") != "VERIFIED_SECURITY_CLAIM_PERSISTED"
    ]

    payload["history"][-1]["state_digest"] = ReasoningGraph._state_digest(
        type(graph.model).from_dict(graph.model.export())
    )
    _rehash_history(payload)

    with pytest.raises(
        ValueError,
        match="canonical security claim must have exactly one persistence event",
    ):
        ReasoningGraph.from_state_dict(payload)


def test_reloaded_graph_rejects_security_claim_event_payload_tampering():
    graph = _verified_claim_state()
    payload = graph.export_state()
    event = next(
        event
        for event in payload["history"]
        if event.get("type") == "VERIFIED_SECURITY_CLAIM_PERSISTED"
    )
    event["claim_fingerprint"] = "tampered"
    _rehash_history(payload)

    with pytest.raises(
        ValueError,
        match="verified security claim event does not match canonical claim",
    ):
        ReasoningGraph.from_state_dict(payload)
