from datetime import datetime, timezone

import pytest

from cydra.evidence import Evidence, EvidenceKind, EvidenceStore, Provenance
from cydra.invariants import Invariant, InvariantRegistry, InvariantStatus


def test_invariant_preserves_inferred_status_and_sources():
    invariant = Invariant(
        "inv-1", "Only authorized identities may mutate resource", InvariantStatus.INFERRED,
        ("recon:auth:1",), 0.7,
    )
    registry = InvariantRegistry()
    registry.add(invariant)
    assert registry.get("inv-1").status is InvariantStatus.INFERRED
    assert registry.get("inv-1").source_ids == ("recon:auth:1",)


def test_invariant_rejects_invalid_confidence():
    with pytest.raises(ValueError):
        Invariant("inv-1", "x", confidence=1.1)


def test_evidence_requires_timezone_aware_provenance():
    with pytest.raises(ValueError):
        Provenance("repo:file.py", datetime.now(), "recon", "IN_SCOPE")


def test_evidence_store_is_append_only_and_preserves_provenance():
    store = EvidenceStore()
    evidence = Evidence(
        "ev-1", EvidenceKind.RECON, {"path": "app.py"},
        Provenance("repo:app.py", datetime.now(timezone.utc), "recon", "IN_SCOPE"),
    )
    store.add(evidence)
    assert store.get("ev-1").provenance.source == "repo:app.py"
    with pytest.raises(ValueError):
        store.add(evidence)
