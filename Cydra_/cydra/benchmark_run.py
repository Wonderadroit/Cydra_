from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence

from .benchmark_corpus import BenchmarkCorpusEntry
from .benchmark_materialization import MaterializedBenchmarkInput, validate_materialized_input


class BenchmarkRunError(ValueError):
    """Raised when a blind benchmark run violates its execution contract."""


@dataclass(frozen=True)
class BlindRunReceipt:
    """Immutable receipt for a completed blind CYDRA invocation.

    The receipt contains only run/provenance metadata and a digest of the sealed
    candidate output. Historical findings are intentionally absent.
    """

    case_id: str
    corpus_fingerprint: str
    materialization_fingerprint: str
    runner_revision: str
    command: tuple[str, ...]
    exit_code: int
    started_at_ns: int
    finished_at_ns: int
    candidate_output_sha256: str
    candidate_output_bytes: int

    @property
    def duration_ns(self) -> int:
        return self.finished_at_ns - self.started_at_ns

    def fingerprint(self) -> str:
        payload = {
            "case_id": self.case_id,
            "corpus_fingerprint": self.corpus_fingerprint,
            "materialization_fingerprint": self.materialization_fingerprint,
            "runner_revision": self.runner_revision,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "started_at_ns": self.started_at_ns,
            "finished_at_ns": self.finished_at_ns,
            "candidate_output_sha256": self.candidate_output_sha256,
            "candidate_output_bytes": self.candidate_output_bytes,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_json(self) -> str:
        payload = {
            "case_id": self.case_id,
            "corpus_fingerprint": self.corpus_fingerprint,
            "materialization_fingerprint": self.materialization_fingerprint,
            "runner_revision": self.runner_revision,
            "command": list(self.command),
            "exit_code": self.exit_code,
            "started_at_ns": self.started_at_ns,
            "finished_at_ns": self.finished_at_ns,
            "duration_ns": self.duration_ns,
            "candidate_output_sha256": self.candidate_output_sha256,
            "candidate_output_bytes": self.candidate_output_bytes,
            "fingerprint": self.fingerprint(),
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _clean_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build a blind-run environment without oracle/ground-truth hints."""
    env = dict(os.environ)
    for key in tuple(env):
        upper = key.upper()
        if "ORACLE" in upper or "GROUND_TRUTH" in upper or "KNOWN_ISSUE" in upper:
            env.pop(key, None)
    if extra:
        forbidden = {
            key
            for key in extra
            if any(token in key.upper() for token in ("ORACLE", "GROUND_TRUTH", "KNOWN_ISSUE"))
        }
        if forbidden:
            raise BenchmarkRunError("blind-run environment may not contain oracle/ground-truth variables")
        env.update(extra)
    return env


def run_blind_command(
    case: BenchmarkCorpusEntry,
    materialized: MaterializedBenchmarkInput,
    staging_root: Path,
    *,
    command: Sequence[str],
    runner_revision: str,
    candidate_output: Path,
    environment: Mapping[str, str] | None = None,
) -> BlindRunReceipt:
    """Run a caller-supplied CYDRA command from the blind staging directory.

    The oracle is not loaded, passed as an argument, or injected into the
    environment. The command runs with the staging directory as its cwd and the
    candidate output is sealed before a receipt is returned.
    """
    staging = Path(staging_root).resolve()
    validate_materialized_input(case, staging, materialized)
    if not command:
        raise BenchmarkRunError("blind-run command must not be empty")
    if not runner_revision.strip():
        raise BenchmarkRunError("runner_revision must not be empty")

    output = Path(candidate_output).resolve()
    try:
        output.relative_to(staging)
    except ValueError as exc:
        raise BenchmarkRunError("candidate output must be inside the blind staging directory") from exc
    if output == staging:
        raise BenchmarkRunError("candidate output must be a file, not the staging directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise BenchmarkRunError("candidate output must not already exist")

    env = _clean_environment(environment)
    env["CYDRA_BLIND_CASE_ID"] = case.case_id
    env["CYDRA_BLIND_CORPUS_FINGERPRINT"] = materialized.corpus_fingerprint
    env["CYDRA_BLIND_MATERIALIZATION_FINGERPRINT"] = materialized.fingerprint()
    env["CYDRA_BLIND_INPUT_ROOT"] = str(staging)
    env["CYDRA_BLIND_CANDIDATE_OUTPUT"] = str(output)

    started = time.time_ns()
    completed = subprocess.run(
        tuple(command),
        cwd=staging,
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    finished = time.time_ns()

    if completed.returncode != 0:
        raise BenchmarkRunError(
            f"blind CYDRA command failed with exit code {completed.returncode}: {completed.stdout[-4000:]}"
        )
    if not output.is_file():
        raise BenchmarkRunError("blind CYDRA command completed without producing candidate output")

    payload = output.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return BlindRunReceipt(
        case_id=case.case_id,
        corpus_fingerprint=materialized.corpus_fingerprint,
        materialization_fingerprint=materialized.fingerprint(),
        runner_revision=runner_revision,
        command=tuple(command),
        exit_code=completed.returncode,
        started_at_ns=started,
        finished_at_ns=finished,
        candidate_output_sha256=digest,
        candidate_output_bytes=len(payload),
    )
