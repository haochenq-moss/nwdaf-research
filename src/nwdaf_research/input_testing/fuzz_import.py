from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from nwdaf_research.input_testing.records import (
    InputCase,
    RunLabel,
    TestOutcome,
    read_jsonl,
    validate_campaign,
    write_jsonl,
)


_MODEL_SLUG = re.compile(r"[^a-zA-Z0-9]+")


def _model_slug(model: str) -> str:
    return _MODEL_SLUG.sub("_", model).strip("_").lower()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_corpus_file(source_campaign: Path, record: dict[str, Any]) -> Path:
    parser = record["parser"]
    arm = record["seed_arm"]
    filename = record["file"]
    matches = sorted(source_campaign.glob(f"corpora/*/{parser}/{arm}/{filename}"))
    expected_model = record.get("model")
    if expected_model:
        expected_slug = _model_slug(expected_model)
        matches = [path for path in matches if path.parts[-4] == expected_slug]
    verified = []
    for path in matches:
        payload = path.read_bytes()
        if len(payload) == record["size_bytes"] and hashlib.sha256(payload).hexdigest() == record["sha256"]:
            verified.append(path)
    if not verified:
        raise ValueError(f"no corpus file matches manifest hash/size: {parser}/{arm}/{filename}")
    if expected_model and len(verified) != 1:
        raise ValueError(f"ambiguous model-specific corpus file for {expected_model}: {filename}")
    return verified[0]


def _validate_corpus_record(record: Any) -> None:
    if not isinstance(record, dict):
        raise ValueError("each corpus manifest entry must be an object")
    required = {"file", "parser", "seed_arm", "sha256", "size_bytes"}
    if not required <= set(record):
        raise ValueError(f"corpus manifest entry missing fields: {sorted(required - set(record))}")
    if not isinstance(record["file"], str) or Path(record["file"]).name != record["file"]:
        raise ValueError("corpus manifest file must be a basename")
    if not isinstance(record["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
        raise ValueError("corpus manifest sha256 must be lowercase hexadecimal")
    if isinstance(record["size_bytes"], bool) or not isinstance(record["size_bytes"], int) or record["size_bytes"] < 1:
        raise ValueError("corpus manifest size_bytes must be a positive integer")


def import_afl_matrix_campaign(
    source_campaign: str | Path,
    output_campaign: str | Path,
) -> dict[str, Any]:
    """Copy verified AFL seed cases into an NWDAF campaign without inventing replay data.

    This importer creates only input_cases.jsonl, copied exact corpus files, and
    fuzz_source_manifest.json. outcomes.jsonl, run_labels.jsonl, and NWDAF run
    directories remain absent until a separately authorized replay is observed.
    """
    source = Path(source_campaign).resolve()
    output = Path(output_campaign).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("source and destination campaign trees must not overlap")
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing campaign: {output}")

    manifest_path = source / "matrix_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"AFL matrix manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") not in {"afl-multimodel-seed-study-v1", "afl-multimodel-seed-study-v2"}:
        raise ValueError(f"unsupported AFL matrix manifest schema: {manifest.get('schema_version')!r}")
    commit = manifest.get("free5gc_commit")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("matrix manifest must contain a pinned hexadecimal free5gc_commit")
    corpus_records = manifest.get("corpora")
    if not isinstance(corpus_records, list) or not corpus_records:
        raise ValueError("matrix manifest has no corpus records")
    for record in corpus_records:
        _validate_corpus_record(record)

    output.parent.mkdir(parents=True, exist_ok=True)
    cases: list[InputCase] = []
    source_records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    with tempfile.TemporaryDirectory(prefix=f".{output.name}.import-", dir=output.parent) as staging_name:
        staging = Path(staging_name)
        for record in corpus_records:
            parser = record["parser"]
            arm = record["seed_arm"]
            if parser not in {"gmm", "gsm"} or arm not in {"ordinary", "llm"}:
                raise ValueError(f"unsupported parser or seed arm in corpus record: {record}")
            model = record.get("model")
            if arm == "llm" and (not isinstance(model, str) or not model.strip()):
                raise ValueError("LLM corpus records must identify their generator model")
            input_source = "ordinary" if arm == "ordinary" else "llm_suggested"
            source_file = _resolve_corpus_file(source, record)
            payload = source_file.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            model_identity = _model_slug(model) if input_source == "llm_suggested" else "curated"
            unique_key = (parser, input_source, model_identity, digest)
            if unique_key in seen:
                continue
            seen.add(unique_key)

            input_id = f"nas-{parser}-{model_identity}-{digest[:16]}"
            relative_target = Path("corpus") / ("ordinary" if input_source == "ordinary" else "llm") / f"{input_id}.bin"
            target = staging / relative_target
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)
            cases.append(InputCase(
                input_id=input_id,
                input_source=input_source,
                component=f"free5GC NAS {parser.upper()} parser",
                input_sha256=digest,
                corpus_path=relative_target.as_posix(),
                free5gc_commit=commit,
                generator_model=model if input_source == "llm_suggested" else None,
                trial_group=f"{manifest.get('seed_strategy', 'unknown')}-{parser}-{model_identity}",
            ))
            source_records.append({
                "input_id": input_id,
                "sha256": digest,
                "size_bytes": len(payload),
                "source_campaign_id": source.name,
                "source_manifest": "matrix_manifest.json",
                "source_corpus_path": source_file.relative_to(source).as_posix(),
                "parser": parser,
                "seed_arm": arm,
                "generator_model": model,
                "seed_strategy": manifest.get("seed_strategy"),
            })

        if not cases:
            raise ValueError("no unique AFL input cases imported")
        write_jsonl(staging / "input_cases.jsonl", cases)
        sidecar = {
            "schema_version": "fuzz-to-nwdaf-source-v1",
            "source_campaign_id": source.name,
            "source_manifest": "matrix_manifest.json",
            "source_artifacts": {
                name: {"path": path.name, "sha256": _sha256_file(path)}
                for name, path in (
                    ("matrix_manifest", manifest_path),
                    ("matrix_run_config", source / "matrix_run_config.json"),
                    ("matrix_results", source / "matrix_results.json"),
                )
                if path.is_file()
            },
            "free5gc_commit": commit,
            "harness_path": manifest.get("harness_path"),
            "harness_sha256": manifest.get("harness_sha256"),
            "seed_strategy": manifest.get("seed_strategy"),
            "models": manifest.get("models", []),
            "parsers": manifest.get("parsers", []),
            "seeds_per_arm_per_parser": manifest.get("seeds_per_arm_per_parser"),
            "input_case_count": len(cases),
            "inputs": source_records,
            "network_replay": "not_performed",
            "telemetry": "not_collected",
            "interpretation": "Imported corpus inputs and provenance only; this is not a network execution outcome or NWDAF detection result.",
        }
        (staging / "fuzz_source_manifest.json").write_text(
            json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (staging / "README.md").write_text(
            f"# Imported NAS Fuzz Inputs\n\n"
            f"This campaign stages {len(cases)} verified seed inputs from the "
            f"`{source.name}` AFL++ campaign for the Fuzz-to-NWDAF evidence workflow.\n\n"
            "This is input/provenance staging only. No network replay was performed; "
            "no `outcomes.jsonl`, `run_labels.jsonl`, or NWDAF `runs/` were created. "
            "Do not run campaign evaluation until actual authorized replay records "
            "and observed telemetry bundles have been added. A parser crash or fuzz "
            "coverage increase is not by itself a bug or vulnerability finding.\n\n"
            "`input_cases.jsonl` links each case to an exact corpus file and SHA-256. "
            "`fuzz_source_manifest.json` preserves the source matrix manifest, run "
            "configuration/results hashes when present, free5GC commit, harness, "
            "seed arm, and generator model.\n",
            encoding="utf-8",
        )
        staging.rename(output)
    return sidecar


def record_live_nas_replay(
    campaign_dir: str | Path,
    *,
    input_id: str,
    payload: bytes,
    free5gc_commit: str,
    run_id: str,
    window_start: str,
    window_end: str,
    outcome_status: str,
    evidence: dict[str, Any],
    exit_code: int | None = None,
) -> dict[str, Any]:
    """Record one observed NAS replay without manufacturing telemetry records."""
    campaign = Path(campaign_dir).resolve()
    if not campaign.is_dir():
        raise FileNotFoundError(f"NWDAF campaign directory not found: {campaign}")
    cases_path = campaign / "input_cases.jsonl"
    outcomes_path = campaign / "outcomes.jsonl"
    labels_path = campaign / "run_labels.jsonl"
    if not cases_path.is_file():
        raise FileNotFoundError(f"campaign manifest not found: {cases_path}")
    if not payload or len(payload) > 4096:
        raise ValueError("live NAS payload must contain 1..4096 bytes")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", input_id):
        raise ValueError("input_id must be a safe campaign identifier")
    if outcome_status not in {"accepted", "rejected", "error", "timeout", "crash"}:
        raise ValueError("unsupported replay outcome status")

    digest = hashlib.sha256(payload).hexdigest()
    case = InputCase(
        input_id=input_id,
        input_source="ordinary",
        component="free5GC NAS GMM via isolated NGAP probe",
        input_sha256=digest,
        corpus_path=f"corpus/ordinary/{input_id}.bin",
        free5gc_commit=free5gc_commit,
        trial_group="live-nas-replay",
        replicate_index=1,
    )
    start = datetime.fromisoformat(window_start.replace("Z", "+00:00"))
    end = datetime.fromisoformat(window_end.replace("Z", "+00:00"))
    outcome = TestOutcome(
        outcome_id=f"outcome-{run_id}",
        input_id=input_id,
        run_id=run_id,
        window_start=window_start,
        window_end=window_end,
        status=outcome_status,
        exit_code=exit_code,
        duration_ms=(end - start).total_seconds() * 1000,
    )
    label = RunLabel(run_id=run_id, label="input_test", split="train")

    cases = read_jsonl(cases_path, InputCase)
    outcomes = read_jsonl(outcomes_path, TestOutcome) if outcomes_path.is_file() else []
    labels = read_jsonl(labels_path, RunLabel) if labels_path.is_file() else []
    validate_campaign(cases + [case], outcomes + [outcome], labels + [label])

    corpus_file = campaign / case.corpus_path
    if corpus_file.exists():
        raise FileExistsError(f"refusing to overwrite replay input: {corpus_file}")
    corpus_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_files: list[tuple[Path, Path]] = []

    def stage_jsonl(path: Path, records: list[Any]) -> None:
        temp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=campaign, prefix=f".{path.name}.", delete=False
        )
        temp_path = Path(temp.name)
        with temp:
            for record in records:
                temp.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        temporary_files.append((temp_path, path))

    replay_record = {
        "schema_version": "nas-live-replay-v1",
        "run_id": run_id,
        "input_id": input_id,
        "input_sha256": digest,
        "input_hex": payload.hex(),
        "input_size_bytes": len(payload),
        "free5gc_commit": free5gc_commit,
        "window_start": window_start,
        "window_end": window_end,
        "execution_outcome": outcome_status,
        "network_replay": "performed_once",
        "telemetry_status": "not_collected_as_nwdaf_run",
        "bug_review": "unreviewed",
        "security_review": "not_assessed",
        "evidence": evidence,
    }
    evidence_path = campaign / "network_replay_observations.jsonl"
    existing_evidence = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""
    evidence_temp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=campaign, prefix=f".{evidence_path.name}.", delete=False
    )
    evidence_temp_path = Path(evidence_temp.name)
    with evidence_temp:
        evidence_temp.write(existing_evidence)
        evidence_temp.write(json.dumps(replay_record, sort_keys=True) + "\n")
    temporary_files.append((evidence_temp_path, evidence_path))

    try:
        corpus_fd, corpus_temp_name = tempfile.mkstemp(prefix=f".{corpus_file.name}.", dir=corpus_file.parent)
        os.close(corpus_fd)
        corpus_temp = Path(corpus_temp_name)
        corpus_temp.write_bytes(payload)
        temporary_files.append((corpus_temp, corpus_file))
        stage_jsonl(cases_path, cases + [case])
        stage_jsonl(outcomes_path, outcomes + [outcome])
        stage_jsonl(labels_path, labels + [label])
        for staged, destination in temporary_files:
            staged.replace(destination)
    except Exception:
        for staged, _ in temporary_files:
            staged.unlink(missing_ok=True)
        raise
    return replay_record


def correct_live_nas_replay_payload(
    campaign_dir: str | Path,
    *,
    input_id: str,
    payload: bytes,
) -> dict[str, str]:
    """Correct imported replay bytes only if current corpus and sidecar agree first."""
    campaign = Path(campaign_dir).resolve()
    cases_path = campaign / "input_cases.jsonl"
    evidence_path = campaign / "network_replay_observations.jsonl"
    if not cases_path.is_file() or not evidence_path.is_file():
        raise FileNotFoundError("campaign lacks input_cases.jsonl or network_replay_observations.jsonl")
    if not payload or len(payload) > 4096:
        raise ValueError("live NAS payload must contain 1..4096 bytes")
    cases = read_jsonl(cases_path, InputCase)
    matches = [case for case in cases if case.input_id == input_id]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one input case for {input_id!r}")
    case = matches[0]
    corpus_file = campaign / case.corpus_path
    existing_payload = corpus_file.read_bytes()
    old_digest = hashlib.sha256(existing_payload).hexdigest()
    if old_digest != case.input_sha256:
        raise ValueError("refusing correction: current corpus bytes do not match recorded input hash")
    new_digest = hashlib.sha256(payload).hexdigest()

    evidence_records = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    matching_evidence = [record for record in evidence_records if record.get("input_id") == input_id]
    if len(matching_evidence) != 1 or matching_evidence[0].get("input_sha256") != old_digest:
        raise ValueError("refusing correction: replay evidence does not uniquely match the current input hash")
    updated_evidence = dict(matching_evidence[0])
    updated_evidence["input_sha256"] = new_digest
    updated_evidence["input_size_bytes"] = len(payload)
    updated_evidence["input_hex"] = payload.hex()
    evidence_records[evidence_records.index(matching_evidence[0])] = updated_evidence

    updated_cases = [replace(item, input_sha256=new_digest) if item.input_id == input_id else item for item in cases]
    corpus_fd, corpus_temp_name = tempfile.mkstemp(prefix=f".{corpus_file.name}.", dir=corpus_file.parent)
    os.close(corpus_fd)
    corpus_temp = Path(corpus_temp_name)
    corpus_temp.write_bytes(payload)

    staged: list[tuple[Path, Path]] = [(corpus_temp, corpus_file)]
    try:
        for target, content in (
            (cases_path, "".join(json.dumps(asdict(item), sort_keys=True) + "\n" for item in updated_cases)),
            (evidence_path, "".join(json.dumps(record, sort_keys=True) + "\n" for record in evidence_records)),
        ):
            temp = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=campaign, prefix=f".{target.name}.", delete=False
            )
            temp_path = Path(temp.name)
            with temp:
                temp.write(content)
            staged.append((temp_path, target))
        for temp_path, target in staged:
            temp_path.replace(target)
    except Exception:
        for temp_path, _ in staged:
            temp_path.unlink(missing_ok=True)
        raise
    return {"old_sha256": old_digest, "new_sha256": new_digest, "input_id": input_id}