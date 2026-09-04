import pytest

from cydra.program_intake import (
    AcquiredResource,
    AcquisitionState,
    AuthorityClass,
    ProgramAssertion,
    ResourceKind,
    ScopeStatus,
    build_program_contract,
    canonical_resource_id,
    classify_link,
    content_fingerprint,
    resource_from_acquisition,
    unresolved_resource,
)


def test_acquired_program_contract_is_ready_and_fingerprinted():
    locator = "https://immunefi.com/bug-bounty/example/scope/"
    program = resource_from_acquisition(
        kind=ResourceKind.PROGRAM,
        acquired=AcquiredResource(locator, "program snapshot", "live-test"),
        adapter="immunefi-fixture",
        authority=AuthorityClass.AUTHORITATIVE,
    )
    contract = build_program_contract(
        program_id="example",
        display_name="Example",
        primary_locator=locator,
        resources=(program,),
        assertions=(ProgramAssertion("a1", "rule", "PoC required", program.resource_id, AuthorityClass.AUTHORITATIVE),),
    )
    assert contract.ready_for_active_testing
    assert len(contract.fingerprint) == 64
    assert contract.to_json().endswith("\n")


def test_required_unresolved_resource_blocks_active_testing():
    locator = "https://immunefi.com/bug-bounty/example/scope/"
    program = unresolved_resource(
        kind=ResourceKind.PROGRAM,
        locator=locator,
        adapter="immunefi",
        authority=AuthorityClass.AUTHORITATIVE,
    )
    contract = build_program_contract(
        program_id="example", display_name="Example", primary_locator=locator, resources=(program,)
    )
    assert program.state is AcquisitionState.UNRESOLVED
    assert not contract.ready_for_active_testing
    assert program.resource_id in contract.unresolved_required


def test_out_of_scope_context_resource_does_not_become_authorized():
    program_locator = "https://immunefi.com/bug-bounty/example/scope/"
    program = resource_from_acquisition(
        kind=ResourceKind.PROGRAM,
        acquired=AcquiredResource(program_locator, "program", "fixture"),
        adapter="immunefi",
        authority=AuthorityClass.AUTHORITATIVE,
    )
    dependency = resource_from_acquisition(
        kind=ResourceKind.REPOSITORY,
        acquired=AcquiredResource("https://github.com/example/dependency", "code", "fixture", "abc123"),
        adapter="github",
        authority=AuthorityClass.PROJECT,
        parent_resource_id=program.resource_id,
        scope=ScopeStatus.OUT_OF_SCOPE,
        required=False,
        reason="contextual dependency of in-scope target",
    )
    contract = build_program_contract(
        program_id="example", display_name="Example", primary_locator=program_locator,
        resources=(program, dependency),
    )
    assert contract.ready_for_active_testing
    assert dependency.scope is ScopeStatus.OUT_OF_SCOPE
    assert dependency.required is False


def test_unknown_scope_never_becomes_in_scope():
    program_locator = "https://immunefi.com/bug-bounty/example/scope/"
    program = resource_from_acquisition(
        kind=ResourceKind.PROGRAM,
        acquired=AcquiredResource(program_locator, "program", "fixture"),
        adapter="immunefi", authority=AuthorityClass.AUTHORITATIVE,
    )
    unknown = unresolved_resource(
        kind=ResourceKind.REPOSITORY,
        locator="https://github.com/example/unknown",
        adapter="github", authority=AuthorityClass.PROJECT,
        parent_resource_id=program.resource_id, required=False,
    )
    assert unknown.scope is ScopeStatus.UNKNOWN
    assert unknown.scope is not ScopeStatus.IN_SCOPE


def test_link_classification_is_conservative_and_non_authorizing():
    assert classify_link("https://github.com/example/repo")[1] is ResourceKind.REPOSITORY
    assert classify_link("https://immunefi.com/bug-bounty/example/scope/")[0] is AuthorityClass.AUTHORITATIVE
    assert classify_link("https://example.com/random")[0] is AuthorityClass.UNKNOWN


def test_content_fingerprint_is_deterministic():
    assert content_fingerprint("abc") == content_fingerprint(b"abc")
    assert len(content_fingerprint("abc")) == 64


def test_primary_resource_identity_is_canonical():
    assert canonical_resource_id(ResourceKind.PROGRAM, "x") == canonical_resource_id(ResourceKind.PROGRAM, "x")
    with pytest.raises(ValueError):
        canonical_resource_id(ResourceKind.PROGRAM, "")


def test_contract_persists_as_canonical_program_context_without_authority_grant():
    from cydra.program_intake import contract_to_system_model
    from cydra.graph_semantics import validate_graph

    locator = "https://immunefi.com/bug-bounty/example/scope/"
    program = resource_from_acquisition(
        kind=ResourceKind.PROGRAM,
        acquired=AcquiredResource(locator, "program", "fixture"),
        adapter="immunefi", authority=AuthorityClass.AUTHORITATIVE,
    )
    dependency = resource_from_acquisition(
        kind=ResourceKind.REPOSITORY,
        acquired=AcquiredResource("https://github.com/example/repo", "code", "fixture", "deadbeef"),
        adapter="github", authority=AuthorityClass.PROJECT,
        parent_resource_id=program.resource_id, scope=ScopeStatus.OUT_OF_SCOPE,
        required=False, reason="contextual dependency",
    )
    model = contract_to_system_model(build_program_contract(
        program_id="example", display_name="Example", primary_locator=locator,
        resources=(program, dependency),
    ))
    assert not validate_graph(model)
    program_node = model.nodes["program:immunefi:example"]
    assert program_node.attributes["ready_for_active_testing"]
    assert model.nodes[dependency.resource_id].attributes["scope"] == "OUT_OF_SCOPE"


def test_reference_discovery_is_broader_than_authorization():
    from cydra.program_intake import discover_references
    html = '''<a href="/docs/">docs</a><a href="https://github.com/example/repo">repo</a>
    <a href="https://example.com/dependency">dependency</a><a href="https://github.com/example/repo">dup</a>'''
    parent = canonical_resource_id(ResourceKind.PROGRAM, "https://immunefi.com/bug-bounty/example/scope/")
    discovered = discover_references(parent_resource_id=parent, base_locator="https://immunefi.com/bug-bounty/example/scope/", content=html)
    assert len(discovered) == 3
    resources = tuple(item.to_resource() for item in discovered)
    assert all(r.state is AcquisitionState.UNRESOLVED for r in resources)
    assert all(r.scope is ScopeStatus.UNKNOWN for r in resources)


def test_scope_classification_never_infers_unknown_as_in_scope():
    from cydra.program_intake import classify_scope
    assert classify_scope(locator="https://github.com/example/repo", explicit_in_scope=["https://github.com/example/repo"]) is ScopeStatus.IN_SCOPE
    assert classify_scope(locator="https://github.com/example/other", explicit_in_scope=["https://github.com/example/repo"]) is ScopeStatus.UNKNOWN
    assert classify_scope(locator="https://github.com/example/repo", explicit_out_of_scope=["https://github.com/example/repo"]) is ScopeStatus.OUT_OF_SCOPE


def test_immunefi_adapter_acquires_only_canonical_program_pages():
    from cydra.program_intake import ImmunefiAcquisitionAdapter

    pages = {
        "https://immunefi.com/bug-bounty/demo/information/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/information/", "info", "fixture"
        ),
        "https://immunefi.com/bug-bounty/demo/scope/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/scope/", "scope", "fixture"
        ),
        "https://immunefi.com/bug-bounty/demo/resources/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/resources/", "resources", "fixture"
        ),
    }
    adapter = ImmunefiAcquisitionAdapter(lambda locator: pages[locator])
    assert adapter.program_slug("https://immunefi.com/bug-bounty/demo/") == "demo"
    assert adapter.canonical_locators("https://immunefi.com/bug-bounty/demo/") == tuple(pages)
    acquired = adapter.acquire_program_pages("https://immunefi.com/bug-bounty/demo/scope/")
    assert [item.content for item in acquired] == ["info", "scope", "resources"]


def test_immunefi_adapter_rejects_cross_program_or_non_immunefi_fetch():
    from cydra.program_intake import ImmunefiAcquisitionAdapter

    adapter = ImmunefiAcquisitionAdapter(lambda locator: AcquiredResource("https://example.com/elsewhere", "x", "fixture"))
    with pytest.raises(ValueError):
        adapter.acquire("https://example.com/bug-bounty/demo/scope/")
    with pytest.raises(ValueError):
        adapter.acquire("https://immunefi.com/bug-bounty/demo/scope/")


def test_discovered_explorer_hosts_are_contextual_not_authoritative():
    assert classify_link("https://etherscan.io/address/0xabc")[0] is AuthorityClass.CONTEXTUAL
    assert classify_link("https://etherscan.io/address/0xabc")[1] is ResourceKind.EXPLORER
    assert classify_link("https://docs.example.org/")[1] is ResourceKind.DOCUMENTATION



def test_known_issue_is_first_class_context_and_does_not_grant_authority():
    from cydra.program_intake import (
        KnownIssue, KnownIssueStatus, ProgramResource, ResourceKind,
        AuthorityClass, AcquisitionState, build_program_contract,
        canonical_resource_id, known_issue_excludes_finding,
    )
    source = ProgramResource(
        resource_id=canonical_resource_id(ResourceKind.KNOWN_ISSUES, "https://example.org/security/known-issues"),
        kind=ResourceKind.KNOWN_ISSUES, locator="https://example.org/security/known-issues",
        authority=AuthorityClass.CONTEXTUAL, acquisition_adapter="fixture", state=AcquisitionState.ACQUIRED,
    )
    primary_locator = "https://immunefi.com/bug-bounty/example/scope/"
    primary = ProgramResource(
        resource_id=canonical_resource_id(ResourceKind.PROGRAM, primary_locator),
        kind=ResourceKind.PROGRAM, locator=primary_locator, authority=AuthorityClass.AUTHORITATIVE,
        acquisition_adapter="fixture", state=AcquisitionState.ACQUIRED,
    )
    issue = KnownIssue(
        issue_id="KI-001", title="Previously disclosed withdrawal issue",
        source_resource_id=source.resource_id, status=KnownIssueStatus.INELIGIBLE_KNOWN,
        affected_assets=("vault",),
    )
    contract = build_program_contract(
        program_id="example", display_name="Example", primary_locator=primary_locator,
        resources=(primary, source), known_issues=(issue,),
    )
    assert contract.known_issues == (issue,)
    assert known_issue_excludes_finding(issue)
    assert contract.ready_for_active_testing is True
    assert source.authority is AuthorityClass.CONTEXTUAL


def test_known_issue_context_does_not_make_a_distinct_root_cause_ineligible():
    from cydra.program_intake import KnownIssue, KnownIssueStatus, known_issue_excludes_finding
    issue = KnownIssue(
        issue_id="KI-002", title="Historical issue retained as context",
        source_resource_id="resource:known-issues:source", status=KnownIssueStatus.CONTEXT_ONLY,
    )
    assert known_issue_excludes_finding(issue) is False


def test_known_issue_resource_classification_is_explicit():
    from cydra.program_intake import AuthorityClass, ResourceKind, classify_link
    authority, kind = classify_link("https://project.example/security/known-issues")
    assert authority is AuthorityClass.CONTEXTUAL
    assert kind is ResourceKind.KNOWN_ISSUES


def test_known_issue_requires_exact_identity_and_applicability():
    from cydra.program_intake import KnownIssue, KnownIssueStatus, known_issue_applies
    fp = "a" * 64
    issue = KnownIssue(
        issue_id="KI-003", title="Known withdrawal flaw", source_resource_id="resource:known-issues:source",
        status=KnownIssueStatus.INELIGIBLE_KNOWN, fingerprint=fp,
        affected_assets=("vault",), affected_versions=("v1",),
    )
    assert known_issue_applies(issue, fingerprint=fp, asset="vault", version="v1") is True
    assert known_issue_applies(issue, fingerprint="b" * 64, asset="vault", version="v1") is False
    assert known_issue_applies(issue, fingerprint=fp, asset="router", version="v1") is False
    assert known_issue_applies(issue, fingerprint=fp, asset="vault", version="v2") is False


def test_known_issue_without_version_or_asset_constraints_does_not_invent_them():
    from cydra.program_intake import KnownIssue, KnownIssueStatus, known_issue_applies
    fp = "c" * 64
    issue = KnownIssue(
        issue_id="KI-004", title="Known global issue", source_resource_id="resource:known-issues:source",
        status=KnownIssueStatus.INELIGIBLE_DUPLICATE, fingerprint=fp,
    )
    assert known_issue_applies(issue, fingerprint=fp, asset="anything", version="anything") is True


def test_resolved_or_context_known_issue_never_blocks_current_candidate():
    from cydra.program_intake import KnownIssue, KnownIssueStatus, known_issue_applies
    fp = "d" * 64
    for status in (KnownIssueStatus.RESOLVED_KNOWN, KnownIssueStatus.CONTEXT_ONLY, KnownIssueStatus.UNKNOWN):
        issue = KnownIssue(
            issue_id=f"KI-{status.value}", title="Historical issue", source_resource_id="resource:known-issues:source",
            status=status, fingerprint=fp,
        )
        assert known_issue_applies(issue, fingerprint=fp) is False


def test_parse_immunefi_material_extracts_policy_and_known_issues_without_granting_authority():
    from cydra.program_intake import parse_immunefi_program, KnownIssueStatus

    info = AcquiredResource(
        "https://immunefi.com/bug-bounty/demo/information/",
        """
        <h1>Demo Protocol</h1>
        <h2>Public Disclosure of Known Issues</h2>
        <p>Bug reports covering previously-discovered bugs are not eligible for a reward.</p>
        <ul><li>Unsafe legacy encoding path remains a known issue.</li></ul>
        <h2>Previous Audits</h2>
        <p>Unfixed audit vulnerabilities are not eligible.</p>
        <h2>Proof of Concept (PoC) Requirements</h2>
        <p>A PoC is required.</p>
        """, "fixture",
    )
    scope = AcquiredResource("https://immunefi.com/bug-bounty/demo/scope/", "<h1>Scope</h1>", "fixture")
    resources = AcquiredResource("https://immunefi.com/bug-bounty/demo/resources/", "<h1>Resources</h1>", "fixture")
    parsed = parse_immunefi_program(locator=info.locator, pages=(info, scope, resources))
    assert parsed.program_id == "demo"
    assert any(a.category == "known_issue_policy" for a in parsed.assertions)
    assert any(a.category == "poc_requirement" for a in parsed.assertions)
    assert parsed.known_issues
    assert all(k.status is KnownIssueStatus.INELIGIBLE_KNOWN for k in parsed.known_issues)
    assert all(k.fingerprint is None for k in parsed.known_issues)


def test_known_issue_extraction_does_not_treat_textual_similarity_as_identity():
    from cydra.program_intake import extract_known_issues
    page = AcquiredResource(
        "https://immunefi.com/bug-bounty/demo/information/",
        """
        <h2>Known Issues</h2>
        <p>Previously identified bugs are not eligible for rewards.</p>
        <p>Withdrawal accounting issue in legacy adapter.</p>
        """, "fixture",
    )
    issues = extract_known_issues(acquired=page)
    assert len(issues) == 1
    assert issues[0].status.value == "INELIGIBLE_KNOWN"
    assert issues[0].fingerprint is None


def test_bounded_reference_plan_filters_to_security_relevant_context():
    from cydra.program_intake import bounded_reference_plan
    parent = resource_from_acquisition(
        kind=ResourceKind.RULES,
        acquired=AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/information/",
            '<a href="https://github.com/demo/repo">repo</a>'
            '<a href="https://example.com/social">social</a>'
            '<a href="https://github.com/demo/audits">audits</a>',
            "fixture",
        ),
        adapter="immunefi", authority=AuthorityClass.AUTHORITATIVE,
    )
    refs = bounded_reference_plan(
        parent=parent,
        acquired=AcquiredResource(
            parent.locator,
            '<a href="https://github.com/demo/repo">repo</a>'
            '<a href="https://example.com/social">social</a>'
            '<a href="https://github.com/demo/audits">audits</a>',
            "fixture",
        ),
    )
    assert len(refs) == 2
    assert any(r.kind is ResourceKind.REPOSITORY for r in refs)
    assert any(r.kind is ResourceKind.AUDIT for r in refs)
    assert all(r.authority is not AuthorityClass.AUTHORITATIVE for r in refs)


def test_acquire_reference_preserves_context_and_does_not_grant_scope():
    from cydra.program_intake import acquire_reference, ResourceDiscovery
    parent = "resource:RULES:parent"
    discovery = ResourceDiscovery(
        parent_resource_id=parent,
        locator="https://github.com/demo/repo",
        kind=ResourceKind.REPOSITORY,
        authority=AuthorityClass.PROJECT,
        required=False,
        reason="contextual dependency",
    )
    resource = acquire_reference(
        discovery=discovery,
        fetcher=lambda locator: AcquiredResource(locator, "code", "fixture", "commit-1"),
    )
    assert resource.state is AcquisitionState.ACQUIRED
    assert resource.scope is ScopeStatus.UNKNOWN
    assert resource.parent_resource_id == parent
    assert resource.version == "commit-1"


def test_dependency_graph_expansion_preserves_parent_and_unknown_scope():
    from cydra.program_intake import (
        expand_resource_dependency_graph, resource_from_acquisition,
        AcquiredResource, ResourceKind, AuthorityClass,
    )
    root = resource_from_acquisition(
        kind=ResourceKind.RULES,
        acquired=AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/information/",
            '<a href="https://github.com/demo/repo">repo</a>', "fixture",
        ),
        adapter="immunefi", authority=AuthorityClass.AUTHORITATIVE,
    )
    materials = {root.resource_id: AcquiredResource(
        root.locator, '<a href="https://github.com/demo/repo">repo</a>', "fixture"
    )}
    fetched = {
        "https://github.com/demo/repo": AcquiredResource(
            "https://github.com/demo/repo", '<a href="https://docs.demo/repo">docs</a>', "fixture", "commit-x"
        ),
        "https://docs.demo/repo": AcquiredResource(
            "https://docs.demo/repo", "documentation", "fixture", "rev-y"
        ),
    }
    resources = expand_resource_dependency_graph(
        roots=(root,), acquired=materials, fetcher=lambda locator: fetched[locator], max_depth=2
    )
    repo = next(r for r in resources if r.locator == "https://github.com/demo/repo")
    docs = next(r for r in resources if r.locator == "https://docs.demo/repo")
    assert repo.parent_resource_id == root.resource_id
    assert docs.parent_resource_id == repo.resource_id
    assert repo.scope is ScopeStatus.UNKNOWN
    assert docs.scope is ScopeStatus.UNKNOWN
    assert repo.version == "commit-x"
    assert docs.version == "rev-y"


def test_required_stale_resource_blocks_program_readiness():
    from cydra.program_intake import (
        ProgramResource, ResourceKind, AuthorityClass, AcquisitionState,
        build_program_contract, canonical_resource_id,
    )
    locator = "https://immunefi.com/bug-bounty/demo/scope/"
    primary = ProgramResource(
        resource_id=canonical_resource_id(ResourceKind.PROGRAM, locator),
        kind=ResourceKind.PROGRAM, locator=locator, authority=AuthorityClass.AUTHORITATIVE,
        acquisition_adapter="fixture", state=AcquisitionState.STALE,
    )
    contract = build_program_contract(
        program_id="demo", display_name="Demo", primary_locator=locator, resources=(primary,)
    )
    assert contract.ready_for_active_testing is False
    assert primary.resource_id in contract.unresolved_required


def test_parsed_immunefi_material_materializes_canonical_contract():
    from cydra.program_intake import parse_immunefi_program, contract_from_parsed_immunefi
    pages = (
        AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/information/",
            "<h1>Demo Protocol</h1><h2>Proof of Concept (PoC) Requirements</h2><p>A PoC is required.</p>",
            "fixture",
        ),
        AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/scope/",
            "<h1>Demo Protocol</h1><h2>Assets in Scope</h2><p>Vault</p>",
            "fixture",
        ),
        AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/resources/",
            '<h1>Resources</h1><a href="https://github.com/demo/repo/tree/main/audits">Audits</a>',
            "fixture",
        ),
    )
    parsed = parse_immunefi_program(locator=pages[1].locator, pages=pages)
    contract = contract_from_parsed_immunefi(parsed)
    assert contract.program_id == "demo"
    assert contract.primary_resource_id == canonical_resource_id(ResourceKind.SCOPE, pages[1].locator)
    assert len(contract.resources) == 3
    assert any(a.category == "poc_requirement" for a in contract.assertions)
    assert contract.ready_for_active_testing is True


def test_github_audit_and_known_issue_paths_are_not_misclassified_as_source_code():
    from cydra.program_intake import classify_link
    assert classify_link("https://github.com/project/repo/tree/main/audits")[1] is ResourceKind.AUDIT
    assert classify_link("https://github.com/project/repo/security/known-issues")[1] is ResourceKind.KNOWN_ISSUES
    assert classify_link("https://github.com/project/repo/tree/main/src")[1] is ResourceKind.REPOSITORY


def test_immunefi_adapter_runs_acquisition_to_contract_without_network_semantics():
    from cydra.program_intake import ImmunefiAcquisitionAdapter
    pages = {
        "https://immunefi.com/bug-bounty/demo/information/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/information/",
            "<h1>Demo Protocol</h1><h2>Proof of Concept (PoC) Requirements</h2><p>A PoC is required.</p>",
            "fixture",
        ),
        "https://immunefi.com/bug-bounty/demo/scope/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/scope/",
            "<h1>Demo Protocol</h1><h2>Assets in Scope</h2><p>Vault</p>",
            "fixture",
        ),
        "https://immunefi.com/bug-bounty/demo/resources/": AcquiredResource(
            "https://immunefi.com/bug-bounty/demo/resources/",
            "<h1>Resources</h1><a href=\"https://github.com/demo/repo/tree/main/audits\">Audits</a>",
            "fixture",
        ),
    }
    contract = ImmunefiAcquisitionAdapter(lambda locator: pages[locator]).acquire_contract(
        "https://immunefi.com/bug-bounty/demo/", intake_context="deterministic fixture"
    )
    assert contract.program_id == "demo"
    assert contract.display_name == "Demo Protocol"
    assert contract.ready_for_active_testing is True
    assert any(a.category == "poc_requirement" for a in contract.assertions)
    assert contract.primary_resource_id == canonical_resource_id(ResourceKind.SCOPE, "https://immunefi.com/bug-bounty/demo/scope/")
