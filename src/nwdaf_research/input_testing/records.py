from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import TypeVar


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INPUT_SOURCES = {"ordinary", "llm_suggested"}
_OUTCOMES = {"accepted", "rejected", "error", "timeout", "crash"}
_RUN_LABELS = {"normal", "input_test"}
_SPLITS = {"train", "held_out"}
Record = TypeVar("Record", "InputCase", "TestOutcome", "RunLabel")


def _require_text(name: str, value: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _parse_timestamp(name: str, value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed


@dataclass(frozen=True)
class InputCase:
    input_id: str
    input_source: str
    component: str
    input_sha256: str
    corpus_path: str
    free5gc_commit: str
    generator_model: str | None = None
    auth_context: str | None = None
    trial_group: str | None = None
    replicate_index: int | None = None
    template_choice: int | None = None

    def __post_init__(self) -> None:
        for name in ("input_id", "component", "free5gc_commit"):
            _require_text(name, getattr(self, name))
        if self.input_source not in _INPUT_SOURCES:
            raise ValueError(f"input_source must be one of {sorted(_INPUT_SOURCES)}")
        if not _SHA256.fullmatch(self.input_sha256):
            raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
        path = PurePosixPath(self.corpus_path)
        if path.is_absolute() or ".." in path.parts or not self.corpus_path:
            raise ValueError("corpus_path must be a safe path relative to the campaign")
        if self.input_source == "llm_suggested":
            _require_text("generator_model", self.generator_model or "")
        if self.auth_context is not None:
            _require_text("auth_context", self.auth_context)
        if self.trial_group is not None:
            _require_text("trial_group", self.trial_group)
        if self.replicate_index is not None and self.replicate_index < 1:
            raise ValueError("replicate_index must be positive")
        if self.template_choice is not None and self.template_choice not in range(1, 9):
            raise ValueError("template_choice must be in the range 1..8")


@dataclass(frozen=True)
class TestOutcome:
    outcome_id: str
    input_id: str
    run_id: str
    window_start: str
    window_end: str
    status: str
    exit_code: int | None = None
    signal: str | None = None
    http_status: int | None = None
    duration_ms: float | None = None

    def __post_init__(self) -> None:
        for name in ("outcome_id", "input_id", "run_id"):
            _require_text(name, getattr(self, name))
        start = _parse_timestamp("window_start", self.window_start)
        end = _parse_timestamp("window_end", self.window_end)
        if end <= start:
            raise ValueError("window_end must be later than window_start")
        if self.status not in _OUTCOMES:
            raise ValueError(f"status must be one of {sorted(_OUTCOMES)}")
        if self.status == "timeout" and self.exit_code == 0:
            raise ValueError("a timed-out input cannot have exit_code 0")
        if self.http_status is not None:
            if isinstance(self.http_status, bool) or not 100 <= self.http_status <= 599:
                raise ValueError("http_status must be an HTTP status code from 100 to 599")
            if self.status == "accepted" and not 200 <= self.http_status < 300:
                raise ValueError("accepted HTTP outcomes must have a 2xx status")
            if self.status == "rejected" and not 400 <= self.http_status < 500:
                raise ValueError("rejected HTTP outcomes must have a 4xx status")
        if self.duration_ms is not None:
            if not math.isfinite(self.duration_ms) or self.duration_ms < 0:
                raise ValueError("duration_ms must be a finite, non-negative number")


@dataclass(frozen=True)
class RunLabel:
    run_id: str
    label: str
    split: str

    def __post_init__(self) -> None:
        _require_text("run_id", self.run_id)
        if self.label not in _RUN_LABELS:
            raise ValueError(f"label must be one of {sorted(_RUN_LABELS)}")
        if self.split not in _SPLITS:
            raise ValueError(f"split must be one of {sorted(_SPLITS)}")


def validate_campaign(
    input_cases: list[InputCase],
    outcomes: list[TestOutcome],
    run_labels: list[RunLabel],
) -> None:
    case_ids = [case.input_id for case in input_cases]
    outcome_ids = [outcome.outcome_id for outcome in outcomes]
    run_ids = [label.run_id for label in run_labels]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("input_id values must be unique")
    if len(outcome_ids) != len(set(outcome_ids)):
        raise ValueError("outcome_id values must be unique")
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("each run_id must have exactly one label and split")

    known_cases = set(case_ids)
    run_partitions = {label.run_id: label for label in run_labels}
    for outcome in outcomes:
        if outcome.input_id not in known_cases:
            raise ValueError(f"outcome references unknown input_id: {outcome.input_id}")
        run_label = run_partitions.get(outcome.run_id)
        if run_label is None or run_label.label != "input_test":
            raise ValueError(f"outcome run must be labeled input_test: {outcome.run_id}")


def read_jsonl(path: str | Path, record_type: type[Record]) -> list[Record]:
    records: list[Record] = []
    with Path(path).open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                values = json.loads(text)
                if not isinstance(values, dict):
                    raise ValueError("record must be a JSON object")
                records.append(record_type(**values))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid record in {path} at line {line_number}: {error}") from error
    return records


def write_jsonl(path: str | Path, records: list[InputCase] | list[TestOutcome] | list[RunLabel]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as destination:
        for record in records:
            destination.write(json.dumps(asdict(record), sort_keys=True) + "\n")