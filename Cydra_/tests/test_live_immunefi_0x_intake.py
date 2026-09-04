import json
from pathlib import Path

from cydra.program_intake import (
    AcquiredResource,
    AuthorityClass,
    ProgramAssertion,
    ResourceKind,
    ScopeStatus,
    build_program_contract,
    contract_to_system_model,
    resource_from_acquisition,
)
from cydra.graph_semantics import validate_graph


ROOT = Path(__file__).resolve().parents[1]


def test_live_0x_immunefi_snapshot_builds_complete_context_contract():
    data = json.loads((ROOT / "data/evaluations/immunefi-0x-live-2026-09-04.json").read_text())
    primary = resource_from_acquisition(
        kind=ResourceKind.PROGRAM,
        acquired=AcquiredResource(
            data["primary_locator"],
            json.dumps(data, sort_keys=True),
            "web.current-snapshot.2026-09-04",
        ),
        adapter="immunefi-web-evaluation",
        authority=AuthorityClass.AUTHORITATIVE,
    )
    resources = [primary]
    resources.append(resource_from_acquisition(
        kind=ResourceKind.REPOSITORY,
        acquired=AcquiredResource(data["source_tree"], "0xProject/0x-settler master/src", "github-reference"),
        adapter="github-reference",
        authority=AuthorityClass.PROJECT,
        parent_resource_id=primary.resource_id,
        required=True,
        reason="program resources identify the codebase",
    ))
    resources.append(resource_from_acquisition(
        kind=ResourceKind.DOCUMENTATION,
        acquired=AcquiredResource(data["documentation"], "0x Docs", "project-reference"),
        adapter="controlled-reference",
        authority=AuthorityClass.PROJECT,
        parent_resource_id=primary.resource_id,
        required=True,
        reason="program resources identify documentation",
    ))
    assertions = [
        ProgramAssertion(f"asset:{i}", "asset_in_scope", asset, primary.resource_id, AuthorityClass.AUTHORITATIVE, ScopeStatus.IN_SCOPE)
        for i, asset in enumerate(data["assets_in_scope"])
    ]
    assertions += [
        ProgramAssertion(f"contract:{i}", "contract_in_scope", address, primary.resource_id, AuthorityClass.AUTHORITATIVE, ScopeStatus.IN_SCOPE)
        for i, address in enumerate(data["smart_contract_scope"])
    ]
    assertions += [
        ProgramAssertion(f"out:{i}", "out_of_scope", text, primary.resource_id, AuthorityClass.AUTHORITATIVE, ScopeStatus.OUT_OF_SCOPE)
        for i, text in enumerate(data["out_of_scope"])
    ]
    assertions += [
        ProgramAssertion(f"prohibited:{i}", "prohibited_testing", text, primary.resource_id, AuthorityClass.AUTHORITATIVE)
        for i, text in enumerate(data["prohibited_testing"])
    ]
    assertions += [
        ProgramAssertion("poc", "poc_required", "PoC required", primary.resource_id, AuthorityClass.AUTHORITATIVE),
        ProgramAssertion("testnet", "testing_restriction", "No testing on mainnet/public testnet; local forks only", primary.resource_id, AuthorityClass.AUTHORITATIVE),
    ]
    contract = build_program_contract(
        program_id=data["program_id"],
        display_name=data["display_name"],
        primary_locator=data["primary_locator"],
        resources=resources,
        assertions=assertions,
        intake_context="live Immunefi evaluation snapshot captured 2026-09-04",
    )
    assert contract.ready_for_active_testing
    assert len([a for a in contract.assertions if a.category == "asset_in_scope"]) == 6
    assert len([a for a in contract.assertions if a.category == "contract_in_scope"]) == 7
    assert len([a for a in contract.assertions if a.category == "out_of_scope"]) == len(data["out_of_scope"])
    assert any(a.category == "poc_required" for a in contract.assertions)
    assert any(a.category == "testing_restriction" for a in contract.assertions)

    model = contract_to_system_model(contract)
    assert not validate_graph(model)
    assert model.nodes["program:immunefi:0x"].attributes["ready_for_active_testing"] is True


def test_live_0x_captured_material_runs_through_real_immunefi_adapter_pipeline():
    """Exercise acquisition -> parsing -> bounded reference discovery on the captured live snapshot."""
    from cydra.program_intake import (
        AcquiredResource,
        ImmunefiAcquisitionAdapter,
        ResourceKind,
        ScopeStatus,
        expand_resource_dependency_graph,
    )

    data = json.loads((ROOT / "data/evaluations/immunefi-0x-live-2026-09-04.json").read_text())
    base = "https://immunefi.com/bug-bounty/0x/"
    pages = {
        base + "information/": AcquiredResource(
            base + "information/",
            """<html><h1>0x</h1><h2>Proof of Concept (PoC) Requirements</h2>
            <p>A PoC demonstrating the bug's impact is required.</p>
            <h2>Public Disclosure of Known Issues</h2>
            <p>Bug reports covering previously-discovered bugs are not eligible for a reward.</p>
            <h2>Previous Audits</h2><p>Any unfixed vulnerabilities mentioned in these reports are not eligible.</p></html>""",
            "captured-live-2026-09-04",
        ),
        base + "scope/": AcquiredResource(
            base + "scope/",
            """<html><h1>0x</h1><h2>Assets in Scope</h2>
            <p>Primacy Of Impact</p><p>0x Settler</p><p>Matcha website</p><p>gasless API</p>
            <p>swap API</p><p>DEX Meta Aggregator</p>
            <h2>Out of scope</h2><p>Attacks requiring leaked keys or credentials</p></html>""",
            "captured-live-2026-09-04",
        ),
        base + "resources/": AcquiredResource(
            base + "resources/",
            """<html><h1>0x</h1>
            <a href="https://github.com/0xProject/0x-settler/tree/master/src">source</a>
            <a href="https://0x.org/docs/">docs</a>
            <a href="https://immunefi.com/bug-bounty/0x/information/">information</a>
            <a href="https://immunefi.com/bug-bounty/0x/audits/">audits</a></html>""",
            "captured-live-2026-09-04",
        ),
    }
    children = {
        "https://github.com/0xProject/0x-settler/tree/master/src": AcquiredResource(
            "https://github.com/0xProject/0x-settler/tree/master/src", "<html>source</html>", "captured-reference"
        ),
        "https://0x.org/docs/": AcquiredResource(
            "https://0x.org/docs/", "<html>docs</html>", "captured-reference"
        ),
        "https://immunefi.com/bug-bounty/0x/audits/": AcquiredResource(
            "https://immunefi.com/bug-bounty/0x/audits/", "<html>audit context</html>", "captured-reference"
        ),
    }

    def fetch(locator):
        return pages[locator] if locator in pages else children[locator]

    adapter = ImmunefiAcquisitionAdapter(fetch)
    contract = adapter.acquire_contract(base + "scope/", intake_context="live 0x captured evaluation")

    assert contract.program_id == "0x"
    assert contract.ready_for_active_testing is True
    assert any(a.category == "poc_requirement" for a in contract.assertions)
    assert any(a.category == "known_issue_policy" for a in contract.assertions)
    assert any(a.category == "audit_policy" for a in contract.assertions)

    resources = {r.resource_id: r for r in contract.resources}
    roots = tuple(resources.values())
    expanded = expand_resource_dependency_graph(
        roots=roots,
        acquired={
            r.resource_id: pages[r.locator]
            for r in contract.resources
            if r.locator in pages
        },
        fetcher=fetch,
        max_depth=1,
    )
    assert any(r.kind is ResourceKind.REPOSITORY and r.scope is ScopeStatus.UNKNOWN for r in expanded)
    assert any(r.kind is ResourceKind.DOCUMENTATION and r.scope is ScopeStatus.UNKNOWN for r in expanded)
    assert all(r.scope is not ScopeStatus.IN_SCOPE for r in expanded if r.kind in {ResourceKind.REPOSITORY, ResourceKind.DOCUMENTATION})
