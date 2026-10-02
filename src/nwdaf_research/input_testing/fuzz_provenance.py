from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return parsed


@dataclass(frozen=True)
class FuzzExecution:
    status: str
    exit_code: int | None
    signal: str | None
    timeout_seconds: float
    crash_signature: str | None = None
    artifact_path: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"completed", "crash", "hang", "timeout", "error"}:
            raise ValueError("unsupported fuzz execution status")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.status == "crash" and not (self.signal or self.crash_signature):
            raise ValueError("crash execution requires a signal or crash signature")
        if self.status == "hang" and not self.artifact_path:
            raise ValueError("hang execution requires a reproducible artifact path")


@dataclass(frozen=True)
class CoverageEvidence:
    status: str
    before: int | None
    after: int | None
    delta: int | None
    artifact_path: str | None

    def __post_init__(self) -> None:
        if self.status not in {"collected", "unavailable", "error"}:
            raise ValueError("unsupported coverage status")
        if self.status == "collected":
            if self.before is None or self.after is None or self.delta is None:
                raise ValueError("collected coverage requires before, after, and delta")
            if self.before < 0 or self.after < 0 or self.delta != self.after - self.before:
                raise ValueError("coverage counts/delta are inconsistent")
        elif any(value is not None for value in (self.before, self.after, self.delta)):
            raise ValueError("uncollected coverage values must be null")


@dataclass(frozen=True)
class ReproductionEvidence:
    status: str
    oracle_id: str | None
    artifact_path: str | None

    def __post_init__(self) -> None:
        if self.status not in {"not_attempted", "reproduced", "not_reproduced", "expected_rejection", "inconclusive"}:
            raise ValueError("unsupported reproduction status")
        if self.status == "reproduced" and not (self.oracle_id and self.artifact_path):
            raise ValueError("reproduced behavior requires oracle and replay artifact references")


@dataclass(frozen=True)
class AnalystReview:
    status: str
    reviewer: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"unreviewed", "needs_more_evidence", "confirmed_bug", "not_a_bug"}:
            raise ValueError("unsupported bug review status")
        if self.status == "confirmed_bug" and not (self.reviewer and self.evidence_refs):
            raise ValueError("confirmed bug requires human reviewer and evidence references")


@dataclass(frozen=True)
class SecurityReview:
    status: str
    reviewer: str | None
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status not in {"not_assessed", "not_a_vulnerability", "potential_vulnerability", "confirmed_vulnerability"}:
            raise ValueError("unsupported security review status")
        if self.status in {"potential_vulnerability", "confirmed_vulnerability"} and not (
            self.reviewer and self.evidence_refs
        ):
            raise ValueError("security findings require a human reviewer and evidence references")


@dataclass(frozen=True)
class FuzzRunProvenance:
    run_id: str
    campaign_id: str
    input_id: str
    corpus_path: str
    input_sha256: str
    input_size_bytes: int
    input_source: str
    generator_model: str | None
    free5gc_commit: str
    component: str
    function: str
    harness_path: str
    harness_sha256: str
    fuzz_engine: str
    go_version: str
    platform: str
    config_sha256: str
    seed: int
    max_duration_seconds: float
    max_input_bytes: int
    started_at: str
    ended_at: str
    execution: FuzzExecution
    coverage: CoverageEvidence
    reproduction: ReproductionEvidence
    bug_review: AnalystReview
    security_review: SecurityReview
    schema_version: str = "fuzz-run-v1"

    def __post_init__(self) -> None:
        for name in ("run_id", "campaign_id", "input_id", "corpus_path", "component", "function", "harness_path", "go_version", "platform"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.schema_version != "fuzz-run-v1":
            raise ValueError("unsupported schema version")
        if self.input_source not in {"ordinary", "llm_suggested"}:
            raise ValueError("input_source must be ordinary or llm_suggested")
        if self.input_source == "llm_suggested" and not self.generator_model:
            raise ValueError("LLM input requires generator model provenance")
        if not _SHA256.fullmatch(self.input_sha256) or not _SHA256.fullmatch(self.harness_sha256) or not _SHA256.fullmatch(self.config_sha256):
            raise ValueError("input, harness, and configuration hashes must be lowercase SHA-256")
        if not _COMMIT.fullmatch(self.free5gc_commit):
            raise ValueError("free5gc_commit must be a hexadecimal commit hash")
        if self.fuzz_engine not in {"go-native", "aflplusplus", "other"}:
            raise ValueError("unsupported fuzz engine")
        if self.input_size_bytes < 0 or self.input_size_bytes > self.max_input_bytes:
            raise ValueError("input_size_bytes must be between zero and max_input_bytes")
        if self.max_duration_seconds <= 0 or self.max_input_bytes < 1:
            raise ValueError("fuzz resource limits must be positive")
        if _timestamp(self.ended_at) <= _timestamp(self.started_at):
            raise ValueError("ended_at must be later than started_at")
        if self.bug_review.status == "confirmed_bug" and self.reproduction.status != "reproduced":
            raise ValueError("a bug cannot be confirmed until its behavior is reproduced")
        if self.security_review.status == "confirmed_vulnerability" and self.bug_review.status != "confirmed_bug":
            raise ValueError("a vulnerability cannot be confirmed before a human confirms the underlying bug")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "runId": self.run_id,
            "campaignId": self.campaign_id,
            "source": {
                "inputSource": self.input_source,
                "generatorModel": self.generator_model,
                "free5gcCommit": self.free5gc_commit,
                "harnessPath": self.harness_path,
                "harnessSha256": self.harness_sha256,
                "fuzzEngine": self.fuzz_engine,
            },
            "target": {"component": self.component, "function": self.function, "language": "go"},
            "input": {"inputId": self.input_id, "corpusPath": self.corpus_path,
                      "sha256": self.input_sha256, "sizeBytes": self.input_size_bytes},
            "toolchain": {"goVersion": self.go_version, "platform": self.platform},
            "configuration": {"sha256": self.config_sha256, "seed": self.seed,
                               "maxDurationSeconds": self.max_duration_seconds,
                               "maxInputBytes": self.max_input_bytes},
            "timeWindow": {"start": self.started_at, "end": self.ended_at},
            "execution": {
                "status": self.execution.status,
                "exitCode": self.execution.exit_code,
                "signal": self.execution.signal,
                "timeoutSeconds": self.execution.timeout_seconds,
                "crashSignature": self.execution.crash_signature,
                "artifactPath": self.execution.artifact_path,
            },
            "coverage": {
                "status": self.coverage.status,
                "before": self.coverage.before,
                "after": self.coverage.after,
                "delta": self.coverage.delta,
                "artifactPath": self.coverage.artifact_path,
            },
            "reproduction": {
                "status": self.reproduction.status,
                "oracleId": self.reproduction.oracle_id,
                "artifactPath": self.reproduction.artifact_path,
            },
            "bugReview": {
                "status": self.bug_review.status,
                "reviewer": self.bug_review.reviewer,
                "evidenceRefs": list(self.bug_review.evidence_refs),
            },
            "securityReview": {
                "status": self.security_review.status,
                "reviewer": self.security_review.reviewer,
                "evidenceRefs": list(self.security_review.evidence_refs),
            },
        }