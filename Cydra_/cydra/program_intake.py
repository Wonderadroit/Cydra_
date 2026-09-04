"""Canonical Immunefi-first program intake and contextual acquisition primitives.

Adapters only produce evidence.  This module never grants testing authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Callable, Iterable, Protocol
from urllib.parse import urljoin, urlparse
import re


class AcquisitionState(str, Enum):
    ACQUIRED = "ACQUIRED"
    UNRESOLVED = "UNRESOLVED"
    STALE = "STALE"
    REJECTED = "REJECTED"


class AuthorityClass(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    PLATFORM = "PLATFORM"
    PROJECT = "PROJECT"
    AGGREGATOR = "AGGREGATOR"
    CONTEXTUAL = "CONTEXTUAL"
    UNKNOWN = "UNKNOWN"


class ScopeStatus(str, Enum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"


class ResourceKind(str, Enum):
    PROGRAM = "PROGRAM"
    RULES = "RULES"
    SCOPE = "SCOPE"
    IMPACTS = "IMPACTS"
    REPOSITORY = "REPOSITORY"
    DOCUMENTATION = "DOCUMENTATION"
    DEPLOYMENT = "DEPLOYMENT"
    EXPLORER = "EXPLORER"
    AUDIT = "AUDIT"
    KNOWN_ISSUES = "KNOWN_ISSUES"
    OTHER = "OTHER"


class KnownIssueStatus(str, Enum):
    """Eligibility meaning of a program-published or program-referenced issue."""

    INELIGIBLE_DUPLICATE = "INELIGIBLE_DUPLICATE"
    INELIGIBLE_KNOWN = "INELIGIBLE_KNOWN"
    RESOLVED_KNOWN = "RESOLVED_KNOWN"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class KnownIssue: 
    """A known vulnerability/issue that must not silently become a bounty finding."""

    issue_id: str
    title: str
    source_resource_id: str
    status: KnownIssueStatus
    locator: str | None = None
    fingerprint: str | None = None
    affected_assets: tuple[str, ...] = ()
    affected_versions: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        for name in ("issue_id", "title", "source_resource_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.fingerprint is not None and len(self.fingerprint) != 64:
            raise ValueError("fingerprint must be a SHA-256 hex digest")


@dataclass(frozen=True)
class ProgramAssertion:
    """One material program assertion with explicit provenance."""

    assertion_id: str
    category: str
    text: str
    source_resource_id: str
    authority: AuthorityClass
    scope: ScopeStatus = ScopeStatus.UNKNOWN
    required: bool = True

    def __post_init__(self) -> None:
        for name in ("assertion_id", "category", "text", "source_resource_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True)
class ProgramResource:
    resource_id: str
    kind: ResourceKind
    locator: str
    authority: AuthorityClass
    acquisition_adapter: str
    state: AcquisitionState
    scope: ScopeStatus = ScopeStatus.UNKNOWN
    content_sha256: str | None = None
    version: str | None = None
    parent_resource_id: str | None = None
    required: bool = True
    reason: str = ""

    def __post_init__(self) -> None:
        for name in ("resource_id", "locator", "acquisition_adapter"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.content_sha256 is not None and len(self.content_sha256) != 64:
            raise ValueError("content_sha256 must be a SHA-256 hex digest")


@dataclass(frozen=True)
class ProgramContract:
    """Provenance-bound program context; not itself an execution grant."""

    program_id: str
    platform: str
    display_name: str
    primary_resource_id: str
    resources: tuple[ProgramResource, ...] = ()
    assertions: tuple[ProgramAssertion, ...] = ()
    known_issues: tuple[KnownIssue, ...] = ()
    unresolved_required: tuple[str, ...] = ()
    intake_context: str = ""

    def __post_init__(self) -> None:
        for name in ("program_id", "platform", "display_name", "primary_resource_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        ids = [r.resource_id for r in self.resources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate resource identity")
        assertion_ids = [a.assertion_id for a in self.assertions]
        known_issue_ids = [k.issue_id for k in self.known_issues]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise ValueError("duplicate assertion identity")
        if len(known_issue_ids) != len(set(known_issue_ids)):
            raise ValueError("duplicate known issue identity")
        resource_ids = set(ids)
        if self.primary_resource_id not in resource_ids:
            raise ValueError("primary resource must exist in resources")
        if any(a.source_resource_id not in resource_ids for a in self.assertions):
            raise ValueError("assertion references unknown resource")
        if any(k.source_resource_id not in resource_ids for k in self.known_issues):
            raise ValueError("known issue references unknown resource")
        blocking_required = {
            r.resource_id for r in self.resources
            if r.required and r.state is not AcquisitionState.ACQUIRED
        }
        if not blocking_required.issubset(set(self.unresolved_required)):
            raise ValueError("all required non-acquired resources must be surfaced")

    @property
    def ready_for_active_testing(self) -> bool:
        return not self.unresolved_required and all(
            r.state is AcquisitionState.ACQUIRED or not r.required for r in self.resources
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "program_id": self.program_id,
            "platform": self.platform,
            "display_name": self.display_name,
            "primary_resource_id": self.primary_resource_id,
            "resources": [resource_payload(r) for r in self.resources],
            "assertions": [assertion_payload(a) for a in self.assertions],
            "known_issues": [known_issue_payload(k) for k in self.known_issues],
            "unresolved_required": sorted(self.unresolved_required),
            "intake_context": self.intake_context,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def to_json(self) -> str:
        return json.dumps({
            "program_id": self.program_id,
            "platform": self.platform,
            "display_name": self.display_name,
            "primary_resource_id": self.primary_resource_id,
            "resources": [resource_payload(r) for r in self.resources],
            "assertions": [assertion_payload(a) for a in self.assertions],
            "known_issues": [known_issue_payload(k) for k in self.known_issues],
            "unresolved_required": list(self.unresolved_required),
            "intake_context": self.intake_context,
            "fingerprint": self.fingerprint,
        }, sort_keys=True, indent=2) + "\n"


def resource_payload(resource: ProgramResource) -> dict[str, object]:
    return {
        "resource_id": resource.resource_id,
        "kind": resource.kind.value,
        "locator": resource.locator,
        "authority": resource.authority.value,
        "acquisition_adapter": resource.acquisition_adapter,
        "state": resource.state.value,
        "scope": resource.scope.value,
        "content_sha256": resource.content_sha256,
        "version": resource.version,
        "parent_resource_id": resource.parent_resource_id,
        "required": resource.required,
        "reason": resource.reason,
    }


def assertion_payload(assertion: ProgramAssertion) -> dict[str, object]:
    return {
        "assertion_id": assertion.assertion_id,
        "category": assertion.category,
        "text": assertion.text,
        "source_resource_id": assertion.source_resource_id,
        "authority": assertion.authority.value,
        "scope": assertion.scope.value,
        "required": assertion.required,
    }


def known_issue_payload(issue: KnownIssue) -> dict[str, object]:
    return {
        "issue_id": issue.issue_id,
        "title": issue.title,
        "source_resource_id": issue.source_resource_id,
        "status": issue.status.value,
        "locator": issue.locator,
        "fingerprint": issue.fingerprint,
        "affected_assets": list(issue.affected_assets),
        "affected_versions": list(issue.affected_versions),
        "notes": issue.notes,
    }


def known_issue_excludes_finding(issue: KnownIssue) -> bool:
    """Return whether the issue's declared status can categorically exclude a finding.

    This does not perform semantic similarity. A newly discovered candidate must be
    explicitly bound to the known issue (for example by an exact root-cause fingerprint)
    before this exclusion is applied.
    """
    return issue.status in {
        KnownIssueStatus.INELIGIBLE_DUPLICATE,
        KnownIssueStatus.INELIGIBLE_KNOWN,
    }


def known_issue_applies(
    issue: KnownIssue,
    *,
    fingerprint: str | None = None,
    asset: str | None = None,
    version: str | None = None,
) -> bool:
    """Determine whether a known issue is applicable to a candidate.

    Fingerprint is an exact identity boundary. Asset/version fields narrow applicability
    when the program supplied them; absence of those fields means the program did not
    provide enough information to narrow the issue, so CYDRA must not invent a restriction.
    Resolved/context-only entries never categorically block a current finding.
    """
    if not known_issue_excludes_finding(issue):
        return False
    if fingerprint is not None and issue.fingerprint is not None and fingerprint != issue.fingerprint:
        return False
    if fingerprint is None or issue.fingerprint is None:
        return False
    if issue.affected_assets and (asset is None or asset not in issue.affected_assets):
        return False
    if issue.affected_versions and (version is None or version not in issue.affected_versions):
        return False
    return True


def content_fingerprint(content: bytes | str) -> str:
    payload = content.encode() if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def canonical_resource_id(kind: ResourceKind, locator: str) -> str:
    normalized = locator.strip()
    if not normalized:
        raise ValueError("resource locator must not be empty")
    return f"resource:{kind.value.lower()}:{hashlib.sha256(normalized.encode()).hexdigest()[:24]}"


def normalize_locator(base_locator: str, locator: str) -> str:
    """Resolve a discovered reference without granting scope or authority."""
    return urljoin(base_locator, locator.strip())


def discover_references(*, parent_resource_id: str, base_locator: str, content: str) -> tuple[ResourceDiscovery, ...]:
    """Extract candidate links conservatively; all discovered resources remain unresolved."""
    candidates: list[ResourceDiscovery] = []
    seen: set[tuple[ResourceKind, str]] = set()
    pattern = r"(?i)(?:href|src)\s*=\s*['\"]([^'\"]+)"
    for raw in re.findall(pattern, content):
        locator = normalize_locator(base_locator, raw)
        if urlparse(locator).scheme not in {"http", "https"}:
            continue
        authority, kind = classify_link(locator)
        key = (kind, locator)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(ResourceDiscovery(
            parent_resource_id=parent_resource_id,
            locator=locator,
            kind=kind,
            authority=authority,
            required=False,
            reason="reference discovered from acquired program material; authorization unresolved",
        ))
    return tuple(candidates)


def bounded_reference_plan(
    *,
    parent: ProgramResource,
    acquired: AcquiredResource,
    max_depth: int = 2,
) -> tuple[ResourceDiscovery, ...]:
    """Plan only security-relevant references within a bounded traversal budget.

    Discovery is intentionally broader than authorization. References to audits,
    known issues, repositories, documentation, deployments and explorers may be
    acquired as context, but none becomes test-authorized merely by discovery.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    discovered = discover_references(
        parent_resource_id=parent.resource_id,
        base_locator=acquired.locator,
        content=acquired.content,
    )
    relevant = {
        ResourceKind.REPOSITORY, ResourceKind.DOCUMENTATION, ResourceKind.DEPLOYMENT,
        ResourceKind.EXPLORER, ResourceKind.AUDIT, ResourceKind.KNOWN_ISSUES,
    }
    return tuple(item for item in discovered if item.kind in relevant)


def acquire_reference(
    *,
    discovery: ResourceDiscovery,
    fetcher: DocumentFetcher | Callable[[str], AcquiredResource],
) -> ProgramResource:
    """Acquire one discovered reference while preserving its parent/provenance."""
    result = fetcher.fetch(discovery.locator) if hasattr(fetcher, "fetch") else fetcher(discovery.locator)
    if not isinstance(result, AcquiredResource):
        raise TypeError("reference fetcher must return AcquiredResource")
    return resource_from_acquisition(
        kind=discovery.kind,
        acquired=result,
        adapter="reference-discovery",
        authority=discovery.authority,
        parent_resource_id=discovery.parent_resource_id,
        scope=ScopeStatus.UNKNOWN,
        required=discovery.required,
        reason=discovery.reason,
    )


def expand_resource_dependency_graph(
    *,
    roots: Iterable[ProgramResource],
    acquired: dict[str, AcquiredResource],
    fetcher: DocumentFetcher | Callable[[str], AcquiredResource] | None = None,
    max_depth: int = 2,
) -> tuple[ProgramResource, ...]:
    """Expand security-relevant resource context without widening authorization.

    ``acquired`` contains already fetched material keyed by canonical resource id.
    When a fetcher is supplied, newly discovered relevant references are fetched up to
    ``max_depth``. Every child retains its parent resource id and starts with UNKNOWN
    scope; only an explicit scope classifier may later change that status.
    """
    if max_depth < 0:
        raise ValueError("max_depth must be non-negative")
    resources: dict[str, ProgramResource] = {r.resource_id: r for r in roots}
    contents = dict(acquired)
    frontier = [(r, 0) for r in roots if r.resource_id in contents]
    seen = set(resources)
    while frontier:
        parent, depth = frontier.pop(0)
        material = contents.get(parent.resource_id)
        if material is None or depth >= max_depth:
            continue
        for discovery in bounded_reference_plan(parent=parent, acquired=material, max_depth=max_depth):
            if discovery.locator in {r.locator for r in resources.values()}:
                continue
            child = discovery.to_resource()
            if child.resource_id in seen:
                continue
            seen.add(child.resource_id)
            resources[child.resource_id] = child
            if fetcher is not None:
                raw = fetcher.fetch(discovery.locator) if hasattr(fetcher, "fetch") else fetcher(discovery.locator)
                if not isinstance(raw, AcquiredResource):
                    raise TypeError("reference fetcher must return AcquiredResource")
                fetched = resource_from_acquisition(
                    kind=discovery.kind, acquired=raw, adapter="reference-discovery",
                    authority=discovery.authority, parent_resource_id=discovery.parent_resource_id,
                    scope=ScopeStatus.UNKNOWN, required=discovery.required, reason=discovery.reason,
                )
                resources[child.resource_id] = fetched
                contents[fetched.resource_id] = raw
                frontier.append((fetched, depth + 1))
    return tuple(resources.values())


def classify_scope(*, locator: str, explicit_in_scope: Iterable[str] = (), explicit_out_of_scope: Iterable[str] = ()) -> ScopeStatus:
    """Apply only explicit scope declarations; unknown never becomes in-scope implicitly."""
    normalized = locator.rstrip("/").lower()
    ins = {x.rstrip("/").lower() for x in explicit_in_scope}
    outs = {x.rstrip("/").lower() for x in explicit_out_of_scope}
    if normalized in outs:
        return ScopeStatus.OUT_OF_SCOPE
    if normalized in ins:
        return ScopeStatus.IN_SCOPE
    return ScopeStatus.UNKNOWN


def classify_link(locator: str) -> tuple[AuthorityClass, ResourceKind]:
    """Conservative host/path classification; classification never authorizes testing."""
    parsed = urlparse(locator)
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.lower()
    if host == "immunefi.com" or host.endswith(".immunefi.com"):
        if any(token in path for token in ("scope", "information", "resources", "bug-bounty")):
            return AuthorityClass.AUTHORITATIVE, ResourceKind.RULES
        return AuthorityClass.AUTHORITATIVE, ResourceKind.OTHER
    if host == "github.com" or host.endswith(".github.com"):
        if any(token in path for token in ("audit", "audits", "security-advis", "advisories", "known-issue", "known_issues", "knownissues")):
            return AuthorityClass.CONTEXTUAL, ResourceKind.KNOWN_ISSUES if any(token in path for token in ("known-issue", "known_issues", "knownissues")) else ResourceKind.AUDIT
        return AuthorityClass.PROJECT, ResourceKind.REPOSITORY
    if host in {"etherscan.io", "polygonscan.com", "arbiscan.io", "basescan.org", "optimistic.etherscan.io", "bscscan.com", "snowtrace.io"} or "explorer" in host:
        return AuthorityClass.CONTEXTUAL, ResourceKind.EXPLORER
    if host.startswith("docs.") or any(token in path for token in ("docs", "documentation")):
        return AuthorityClass.CONTEXTUAL, ResourceKind.DOCUMENTATION
    if any(token in path for token in ("known-issue", "known_issues", "known-issues", "knownissues", "security-advisories", "advisories")):
        return AuthorityClass.CONTEXTUAL, ResourceKind.KNOWN_ISSUES
    if any(token in path for token in ("audit", "audits")):
        return AuthorityClass.CONTEXTUAL, ResourceKind.AUDIT
    if any(token in path for token in ("deployment", "deployments", "contract")):
        return AuthorityClass.CONTEXTUAL, ResourceKind.DEPLOYMENT
    return AuthorityClass.UNKNOWN, ResourceKind.OTHER


@dataclass(frozen=True)
class ResourceDiscovery:
    parent_resource_id: str
    locator: str
    kind: ResourceKind
    authority: AuthorityClass
    required: bool
    reason: str

    def to_resource(self, *, adapter: str = "reference-discovery") -> ProgramResource:
        return ProgramResource(
            resource_id=canonical_resource_id(self.kind, self.locator),
            kind=self.kind,
            locator=self.locator,
            authority=self.authority,
            acquisition_adapter=adapter,
            state=AcquisitionState.UNRESOLVED,
            parent_resource_id=self.parent_resource_id,
            required=self.required,
            reason=self.reason,
        )


class DocumentFetcher(Protocol):
    """Injected transport boundary; transport never grants testing authority."""

    def fetch(self, locator: str) -> "AcquiredResource": ...


class ImmunefiAcquisitionAdapter:
    """Acquire the bounded canonical Immunefi program pages.

    The adapter deliberately accepts an injected fetcher so production transport
    and deterministic evaluation fixtures remain separate from program semantics.
    """

    name = "immunefi"
    _PROGRAM_PATTERN = re.compile(r"^/bug-bounty/([^/]+)/?(?:(information|scope|resources)/?)?$")

    def __init__(self, fetcher: DocumentFetcher | Callable[[str], AcquiredResource]):
        self._fetcher = fetcher

    @staticmethod
    def _fetch(fetcher, locator: str) -> AcquiredResource:
        result = fetcher.fetch(locator) if hasattr(fetcher, "fetch") else fetcher(locator)
        if not isinstance(result, AcquiredResource):
            raise TypeError("Immunefi fetcher must return AcquiredResource")
        return result

    @classmethod
    def normalize_program_locator(cls, locator: str) -> str:
        parsed = urlparse(locator.strip())
        if parsed.scheme != "https" or parsed.hostname != "immunefi.com":
            raise ValueError("Immunefi adapter requires an https://immunefi.com program locator")
        match = cls._PROGRAM_PATTERN.match(parsed.path.rstrip("/") + "/")
        if not match:
            raise ValueError("locator is not an Immunefi bug-bounty program URL")
        slug = match.group(1)
        return f"https://immunefi.com/bug-bounty/{slug}/scope/"

    @classmethod
    def program_slug(cls, locator: str) -> str:
        return cls.normalize_program_locator(locator).split("/bug-bounty/", 1)[1].split("/", 1)[0]

    def canonical_locators(self, locator: str) -> tuple[str, str, str]:
        scope = self.normalize_program_locator(locator)
        base = scope.rsplit("/", 2)[0] + "/"
        return (
            f"{base}information/",
            scope,
            f"{base}resources/",
        )

    def acquire(self, locator: str) -> AcquiredResource:
        """Acquire the requested canonical program page without widening scope."""
        canonical = self.normalize_program_locator(locator)
        requested = locator.rstrip("/") + "/"
        if requested != canonical:
            # Non-scope pages are still valid acquisition inputs, but only when
            # they belong to the same canonical program path.
            parsed = urlparse(requested)
            expected = urlparse(canonical)
            if parsed.scheme != expected.scheme or parsed.netloc != expected.netloc:
                raise ValueError("locator is outside the canonical Immunefi program")
            if not parsed.path.startswith(expected.path.rsplit("scope/", 1)[0]):
                raise ValueError("locator is outside the canonical Immunefi program")
            requested = requested
        acquired = self._fetch(self._fetcher, requested)
        if urlparse(acquired.locator).netloc.lower() != "immunefi.com":
            raise ValueError("fetcher returned a non-Immunefi locator")
        return acquired

    def acquire_program_pages(self, locator: str) -> tuple[AcquiredResource, ...]:
        """Acquire information, scope, and resources pages as one bounded unit."""
        pages = []
        for page in self.canonical_locators(locator):
            pages.append(self._fetch(self._fetcher, page))
        return tuple(pages)

    def acquire_contract(self, locator: str, *, intake_context: str = "") -> "ProgramContract":
        """Run canonical Immunefi acquisition and parsing as one bounded operation."""
        pages = self.acquire_program_pages(locator)
        parsed = parse_immunefi_program(locator=locator, pages=pages)
        return contract_from_parsed_immunefi(parsed, intake_context=intake_context)


class ProgramAcquisitionAdapter(Protocol):
    name: str

    def acquire(self, locator: str) -> "AcquiredResource": ...


@dataclass(frozen=True)
class AcquiredResource:
    locator: str
    content: str
    retrieved_context: str
    version: str | None = None

    @property
    def sha256(self) -> str:
        return content_fingerprint(self.content)


def resource_from_acquisition(
    *,
    kind: ResourceKind,
    acquired: AcquiredResource,
    adapter: str,
    authority: AuthorityClass,
    parent_resource_id: str | None = None,
    scope: ScopeStatus = ScopeStatus.UNKNOWN,
    required: bool = True,
    reason: str = "",
) -> ProgramResource:
    return ProgramResource(
        resource_id=canonical_resource_id(kind, acquired.locator),
        kind=kind,
        locator=acquired.locator,
        authority=authority,
        acquisition_adapter=adapter,
        state=AcquisitionState.ACQUIRED,
        scope=scope,
        content_sha256=acquired.sha256,
        version=acquired.version,
        parent_resource_id=parent_resource_id,
        required=required,
        reason=reason,
    )


def unresolved_resource(
    *, kind: ResourceKind, locator: str, adapter: str, authority: AuthorityClass,
    parent_resource_id: str | None = None, required: bool = True, reason: str = "",
) -> ProgramResource:
    return ProgramResource(
        resource_id=canonical_resource_id(kind, locator),
        kind=kind,
        locator=locator,
        authority=authority,
        acquisition_adapter=adapter,
        state=AcquisitionState.UNRESOLVED,
        parent_resource_id=parent_resource_id,
        required=required,
        reason=reason,
    )



@dataclass(frozen=True)
class ParsedImmunefiMaterial:
    """Conservative structured extraction from acquired Immunefi material.

    Extraction produces candidate assertions/context; it never grants testing authority.
    """

    program_id: str
    display_name: str
    resources: tuple[ProgramResource, ...]
    assertions: tuple[ProgramAssertion, ...]
    known_issues: tuple[KnownIssue, ...]


def _visible_text(content: str) -> str:
    """Reduce HTML to deterministic visible-ish text without external dependencies."""
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []
            self.skip = 0
        def handle_starttag(self, tag, attrs):
            if tag in {"script", "style", "noscript", "svg"}:
                self.skip += 1
        def handle_endtag(self, tag):
            if tag in {"script", "style", "noscript", "svg"} and self.skip:
                self.skip -= 1
        def handle_data(self, data):
            if not self.skip and data.strip():
                self.parts.append(data.strip())
    parser = _Parser()
    parser.feed(content)
    return "\n".join(parser.parts)


def _section_lines(text: str, headings: tuple[str, ...]) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    wanted = {h.lower() for h in headings}
    start = None
    for i, line in enumerate(lines):
        if line.lower().rstrip(":") in wanted:
            start = i + 1
            break
    if start is None:
        return []
    stop_words = {
        "rewards", "program overview", "proof of concept (poc) requirements",
        "previous audits", "assets body", "immunefi standard badge",
    }
    out = []
    for line in lines[start:]:
        if line.lower().rstrip(":") in stop_words and out:
            break
        out.append(line)
    return out


def parse_immunefi_material(
    *,
    acquired: AcquiredResource,
    kind: ResourceKind,
    authority: AuthorityClass = AuthorityClass.AUTHORITATIVE,
) -> tuple[ProgramAssertion, ...]:
    """Extract high-value program assertions conservatively from one page."""
    resource_id = canonical_resource_id(kind, acquired.locator)
    text = _visible_text(acquired.content)
    assertions: list[ProgramAssertion] = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lower = text.lower()

    patterns = (
        ("poc_requirement", "proof of concept", "PoC requirement"),
        ("kyc_requirement", "kyc", "KYC requirement"),
        ("testing_restriction", "prohibited", "Testing restriction"),
        ("known_issue_policy", "known issue", "Known-issue policy"),
        ("audit_policy", "previous audits", "Previous-audit policy"),
        ("disclosure_policy", "public disclosure", "Disclosure policy"),
        ("scope_policy", "assets in scope", "Scope policy"),
    )
    for category, needle, label in patterns:
        if needle in lower:
            matched = next((line for line in lines if needle in line.lower()), None)
            value = matched or f"{label} is present in acquired program material."
            assertions.append(ProgramAssertion(
                assertion_id=f"assertion:{category}:{resource_id}",
                category=category,
                text=value,
                source_resource_id=resource_id,
                authority=authority,
                scope=ScopeStatus.UNKNOWN,
                required=False,
            ))

    # Preserve explicit asset/contract declarations as assertions. The parser is
    # intentionally lexical; it does not infer eligibility from arbitrary text.
    for i, line in enumerate(lines):
        if line.lower().startswith("target") or line.lower().startswith("asset"):
            continue
        if "0x" in line and len(line) >= 20 and any(c.isdigit() for c in line):
            assertions.append(ProgramAssertion(
                assertion_id=f"assertion:address:{resource_id}:{i}",
                category="candidate_contract_reference",
                text=line,
                source_resource_id=resource_id,
                authority=authority,
                scope=ScopeStatus.UNKNOWN,
                required=False,
            ))
    return tuple(assertions)


def extract_known_issues(
    *, acquired: AcquiredResource, resource_id: str | None = None
) -> tuple[KnownIssue, ...]:
    """Extract explicit known-issue entries without inventing root-cause identity."""
    source_id = resource_id or canonical_resource_id(ResourceKind.KNOWN_ISSUES, acquired.locator)
    text = _visible_text(acquired.content)
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    marker_indices = [i for i, line in enumerate(lines)
                      if "known issues" in line.lower() or "previously-discovered bugs" in line.lower()]
    if not marker_indices:
        return ()
    start = marker_indices[0] + 1
    stop = len(lines)
    for i in range(start, len(lines)):
        low = lines[i].lower().rstrip(":")
        if low in {"previous audits", "rewards", "proof of concept (poc) requirements", "public disclosure of known issues"}:
            stop = i
            break
    section = lines[start:stop]
    policy_excludes = any(
        "not eligible" in line.lower() or "ineligible" in line.lower()
        for line in section[:12]
    )
    entries: list[KnownIssue] = []
    for line in section:
        low = line.lower()
        if low in {"category", "description / link", "last updated at"} or len(line) < 8:
            continue
        if "known issue" in low and len(line) < 50:
            continue
        if any(token in low for token in (
            "not eligible", "ineligible", "previously identified bugs",
            "previously-discovered bugs", "this includes:",
        )):
            continue
        # Navigation and policy prose are not issues. Keep actual issue-like rows.
        if low.startswith(("category", "status", "last updated", "reports covering", "this includes")):
            continue
        digest = hashlib.sha256(line.encode("utf-8")).hexdigest()
        entries.append(KnownIssue(
            issue_id=f"known:{digest[:24]}",
            title=line[:200],
            source_resource_id=source_id,
            status=(KnownIssueStatus.INELIGIBLE_KNOWN if policy_excludes else KnownIssueStatus.UNKNOWN),
            fingerprint=None,
            notes="Extracted conservatively from program material; exact root-cause identity unresolved.",
        ))
    seen: set[str] = set()
    return tuple(item for item in entries if not (item.issue_id in seen or seen.add(item.issue_id)))


def parse_immunefi_program(
    *, locator: str, pages: Iterable[AcquiredResource]
) -> ParsedImmunefiMaterial:
    """Build bounded, provenance-preserving structure from canonical Immunefi pages."""
    slug = ImmunefiAcquisitionAdapter.program_slug(locator)
    ordered = tuple(pages)
    if not ordered:
        raise ValueError("at least one acquired Immunefi page is required")

    resources: list[ProgramResource] = []
    assertions: list[ProgramAssertion] = []
    known: list[KnownIssue] = []
    for page in ordered:
        path = urlparse(page.locator).path.lower()
        if "/scope/" in path:
            kind = ResourceKind.SCOPE
        elif "/information/" in path:
            kind = ResourceKind.RULES
        elif "/resources/" in path:
            kind = ResourceKind.PROGRAM
        else:
            kind = ResourceKind.OTHER
        resource = resource_from_acquisition(
            kind=kind, acquired=page, adapter="immunefi",
            authority=AuthorityClass.AUTHORITATIVE, required=True,
        )
        resources.append(resource)
        assertions.extend(parse_immunefi_material(acquired=page, kind=kind))
        known.extend(extract_known_issues(acquired=page, resource_id=resource.resource_id))

    # The scope page is the canonical primary resource when present.
    display_name = slug
    for page in ordered:
        title_text = _visible_text(page.content).splitlines()
        for line in title_text[:8]:
            if line and line.lower() not in {"information", "scope", "resources"}:
                display_name = line[:200]
                break
        if display_name != slug:
            break
    return ParsedImmunefiMaterial(
        program_id=slug,
        display_name=display_name,
        resources=tuple(resources),
        assertions=tuple(assertions),
        known_issues=tuple(known),
    )


def contract_from_parsed_immunefi(
    parsed: ParsedImmunefiMaterial, *, intake_context: str = ""
) -> ProgramContract:
    """Materialize parsed Immunefi evidence into the canonical program contract."""
    primary = next((r for r in parsed.resources if r.kind is ResourceKind.SCOPE), None)
    if primary is None:
        primary = parsed.resources[0]
    return build_program_contract(
        program_id=parsed.program_id,
        display_name=parsed.display_name,
        primary_locator=primary.locator,
        resources=parsed.resources,
        assertions=parsed.assertions,
        known_issues=parsed.known_issues,
        platform="Immunefi",
        intake_context=intake_context,
    )

def build_program_contract(
    *,
    program_id: str,
    display_name: str,
    primary_locator: str,
    resources: Iterable[ProgramResource],
    assertions: Iterable[ProgramAssertion] = (),
    known_issues: Iterable[KnownIssue] = (),
    platform: str = "Immunefi",
    intake_context: str = "",
) -> ProgramContract:
    resources_tuple = tuple(resources)
    primary_id = canonical_resource_id(ResourceKind.PROGRAM, primary_locator)
    if not any(r.resource_id == primary_id for r in resources_tuple):
        # Parsed program contracts may designate the canonical scope page as the
        # primary authority. Preserve the resource's actual kind rather than
        # manufacturing a second identity for the same locator.
        matching = next((r for r in resources_tuple if r.locator.rstrip("/") == primary_locator.rstrip("/")), None)
        if matching is None:
            raise ValueError("primary program resource must be supplied")
        primary_id = matching.resource_id
    unresolved = tuple(sorted(
        r.resource_id for r in resources_tuple
        if r.required and r.state is not AcquisitionState.ACQUIRED
    ))
    return ProgramContract(
        program_id=program_id,
        platform=platform,
        display_name=display_name,
        primary_resource_id=primary_id,
        resources=resources_tuple,
        assertions=tuple(assertions),
        known_issues=tuple(known_issues),
        unresolved_required=unresolved,
        intake_context=intake_context,
    )


def contract_to_system_model(contract: ProgramContract, model=None):
    """Persist program intake as canonical context without granting authority."""
    from .system_model import SystemModel, Node

    model = model or SystemModel()
    program_node_id = f"program:{contract.platform.lower()}:{contract.program_id}"
    model.add_node(Node(program_node_id, "program", contract.display_name, {
        "platform": contract.platform,
        "program_id": contract.program_id,
        "intake_fingerprint": contract.fingerprint,
        "ready_for_active_testing": contract.ready_for_active_testing,
        "primary_resource_id": contract.primary_resource_id,
        "unresolved_required": list(contract.unresolved_required),
        "intake_context": contract.intake_context,
    }))
    for resource in contract.resources:
        model.add_node(Node(resource.resource_id, "resource", resource.locator, {
            "kind": resource.kind.value,
            "authority": resource.authority.value,
            "adapter": resource.acquisition_adapter,
            "state": resource.state.value,
            "scope": resource.scope.value,
            "content_sha256": resource.content_sha256,
            "version": resource.version,
            "required": resource.required,
            "reason": resource.reason,
        }))
        model.connect(program_node_id, "contains_resource", resource.resource_id)
        if resource.parent_resource_id and resource.parent_resource_id in model.nodes:
            model.connect(resource.parent_resource_id, "references_resource", resource.resource_id)
    return model
