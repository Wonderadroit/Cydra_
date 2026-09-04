from cydra.causal import CausalLink, verify_causal_chain
from cydra.counterexample import Counterexample, minimize_counterexample


def test_counterexample_preserves_reproducibility_and_evidence():
    original = Counterexample(
        test_name="InvariantVault.totalDeposits",
        input_data={"amount": 1},
        trace=["deposit", "withdraw"],
        invariant="totalDeposits == balance(actor)",
        expected=0,
        actual=1,
        reproducible=True,
    )
    reduced = minimize_counterexample(original)
    assert reduced.as_evidence()["type"] == "COUNTEREXAMPLE"
    assert reduced.reproducible is True
    assert reduced.input_data == {"amount": 1}
    assert reduced.trace == ["deposit", "withdraw"]


def test_causal_chain_requires_evidence():
    invalid = verify_causal_chain([CausalLink("h1", "violates", "i1", [])])
    assert invalid.valid is False


def test_causal_chain_accepts_provenance():
    valid = verify_causal_chain(
        [CausalLink("h1", "violates", "i1", ["evidence:foundry:1"])]
    )
    assert valid.valid is True
