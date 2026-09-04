import subprocess

import pytest

from cydra.external_execution import ExternalExecutionGateway
from cydra.foundry import FoundryAuthorization, FoundryRunner, FoundryResult, result_to_evidence


def test_authorization_context_fails_closed():
    authorization = FoundryAuthorization("audit-123")
    assert authorization.authorized
    assert authorization.scope_status == "AUTHORIZED_EXECUTION"
    with pytest.raises(PermissionError):
        FoundryRunner(".").run_test("testAnything")


def test_standalone_foundry_execution_requires_canonical_gateway_capability(tmp_path):
    authorization = FoundryAuthorization("audit-123")
    runner = FoundryRunner(str(tmp_path))
    request = runner.build_request("testAnything", authorization=authorization, execution_id="exec-direct")
    with pytest.raises(PermissionError, match="canonical external execution gateway"):
        runner.run_test("testAnything", authorization=authorization, execution_id=request.execution_id, request_digest=request.digest)


def test_authorization_rejects_wrong_scope():
    with pytest.raises(ValueError):
        FoundryAuthorization("audit-123", scope_status="IN_SCOPE")


def test_project_fingerprint_is_deterministic_and_excludes_generated_state(tmp_path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "generated.json").write_text("volatile", encoding="utf-8")

    runner = FoundryRunner(str(tmp_path))
    first = runner.project_fingerprint()
    (out / "generated.json").write_text("changed", encoding="utf-8")
    assert runner.project_fingerprint() == first

    (src / "Vault.sol").write_text("contract Vault { uint256 x; }", encoding="utf-8")
    assert runner.project_fingerprint() != first


def test_gateway_bound_foundry_execution_records_external_provenance(monkeypatch, tmp_path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Vault.sol").write_text("contract Vault {}", encoding="utf-8")
    runner = FoundryRunner(str(tmp_path))
    calls = []
    authorization = FoundryAuthorization("audit-123")
    request = runner.build_request("testInvariant", (), authorization=authorization, execution_id="execution:test-1")
    states = {}

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command == ["forge", "--version"]:
            return subprocess.CompletedProcess(command, 0, "forge 1.2.3", "")
        return subprocess.CompletedProcess(command, 1, "FAIL\n", "trace")

    monkeypatch.setattr("cydra.foundry.subprocess.run", fake_run)
    gateway = ExternalExecutionGateway(
        lambda req: None,
        lambda req, state: states.__setitem__(req.digest, state),
        lambda req: states.get(req.digest),
        lambda req, result: None,
    )
    gateway.register("foundry", runner)
    result = gateway.execute("foundry", request, authorization=authorization)

    assert result.counterexample
    assert result.authorization_id == "audit-123"
    assert result.scope_status == "AUTHORIZED_EXECUTION"
    assert result.execution_id == "execution:test-1"
    assert result.project_fingerprint == runner.project_fingerprint()
    assert result.forge_version == "forge 1.2.3"
    assert result.started_at and result.finished_at
    assert result.duration_seconds is not None
    assert calls[0][0] == ("forge", "test", "--match-test", "testInvariant")
    assert calls[0][1]["timeout"] == 300.0
    assert calls[1][0] == ["forge", "--version"]
    assert states[request.digest] == "COMPLETED"

    evidence = result_to_evidence(result, "evidence:forge:1")
    assert evidence.provenance.scope_status == "AUTHORIZED_EXECUTION"
    assert evidence.provenance.details["authorization_id"] == "audit-123"
    assert evidence.provenance.details["execution_id"] == "execution:test-1"
    assert evidence.provenance.details["project_fingerprint"] == result.project_fingerprint


def test_result_to_evidence_rejects_missing_authorization():
    result = FoundryResult(("forge", "test"), 0, "ok", "", execution_id="execution:unauthorized")
    with pytest.raises(PermissionError):
        result_to_evidence(result, "evidence:unauthorized")


def test_result_to_evidence_rejects_non_execution_scope():
    result = FoundryResult(
        ("forge", "test"), 0, "ok", "",
        authorization_id="audit-123", scope_status="IN_SCOPE", execution_id="execution:wrong-scope",
    )
    with pytest.raises(PermissionError):
        result_to_evidence(result, "evidence:wrong-scope")


def test_gateway_bound_timeout_is_inconclusive_not_counterexample(monkeypatch, tmp_path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\n", encoding="utf-8")
    runner = FoundryRunner(str(tmp_path))
    authorization = FoundryAuthorization("audit-123")
    request = runner.build_request(authorization=authorization, execution_id="execution:timeout")
    states = {}

    def fake_run(command, **kwargs):
        if command == ["forge", "--version"]:
            return subprocess.CompletedProcess(command, 0, "forge 1.2.3", "")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial", stderr="timed out")

    monkeypatch.setattr("cydra.foundry.subprocess.run", fake_run)
    gateway = ExternalExecutionGateway(
        lambda req: None,
        lambda req, state: states.__setitem__(req.digest, state),
        lambda req: states.get(req.digest),
        lambda req, result: None,
    )
    gateway.register("foundry", runner)
    result = gateway.execute("foundry", request, authorization=authorization)

    assert result.returncode == 124
    assert result.timed_out
    assert not result.counterexample
    assert result.outcome == "TIMEOUT"
    assert result.duration_seconds is not None
    assert result.stdout == "partial"
    assert result.stderr == "timed out"
    assert states[request.digest] == "COMPLETED"
