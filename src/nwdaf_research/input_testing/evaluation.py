from __future__ import annotations

import statistics
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score

from nwdaf_research.input_testing.records import InputCase, RunLabel, TestOutcome


FEATURE_NAMES = (
    "duration_sec",
    "linux_event_count",
    "linux_load_1m_mean",
    "linux_load_1m_std",
    "linux_load_1m_max",
    "linux_memory_available_mean",
    "memory_available_ratio_mean",
    "process_event_count",
    "sbi_event_count",
    "sbi_error_event_count",
    "sbi_telemetry_available",
    "pfcp_event_count",
    "pfcp_request_count",
    "pfcp_response_count",
    "pfcp_telemetry_available",
    "free5gc_event_count",
    "free5gc_telemetry_available",
    "ebpf_event_count",
    "ebpf_telemetry_available",
)


def compare_input_outcomes(
    input_cases: Sequence[InputCase],
    outcomes: Sequence[TestOutcome],
) -> dict[str, Any]:
    """Summarize observed outcomes for ordinary and LLM-suggested inputs."""
    cases_by_id = {case.input_id: case for case in input_cases}
    if len(cases_by_id) != len(input_cases):
        raise ValueError("input cases must have unique input_id values")

    summaries: dict[str, dict[str, Any]] = {
        source: {
            "input_count": 0,
            "inputs_with_outcomes": 0,
            "outcome_count": 0,
            "status_counts": {status: 0 for status in ("accepted", "rejected", "error", "timeout", "crash")},
            "crash_observation_rate": 0.0,
        }
        for source in ("ordinary", "llm_suggested")
    }
    outcome_input_ids: dict[str, set[str]] = {source: set() for source in summaries}
    outcomes_by_input: dict[str, list[TestOutcome]] = {}
    for case in input_cases:
        summaries[case.input_source]["input_count"] += 1

    for outcome in outcomes:
        case = cases_by_id.get(outcome.input_id)
        if case is None:
            raise ValueError(f"outcome references unknown input_id: {outcome.input_id}")
        summary = summaries[case.input_source]
        summary["outcome_count"] += 1
        summary["status_counts"][outcome.status] += 1
        outcome_input_ids[case.input_source].add(case.input_id)
        outcomes_by_input.setdefault(outcome.input_id, []).append(outcome)

    for source, summary in summaries.items():
        summary["inputs_with_outcomes"] = len(outcome_input_ids[source])
        if summary["outcome_count"]:
            summary["crash_observation_rate"] = (
                summary["status_counts"]["crash"] / summary["outcome_count"]
            )

    cases_by_hash: dict[str, dict[str, list[InputCase]]] = {}
    for case in input_cases:
        cases_by_hash.setdefault(case.input_sha256, {}).setdefault(case.input_source, []).append(case)
    matched_pairs = []
    for digest, sources in sorted(cases_by_hash.items()):
        if "ordinary" not in sources or "llm_suggested" not in sources:
            continue
        for ordinary_case in sources["ordinary"]:
            for llm_case in sources["llm_suggested"]:
                ordinary_results = outcomes_by_input.get(ordinary_case.input_id, [])
                llm_results = outcomes_by_input.get(llm_case.input_id, [])
                if len(ordinary_results) != 1 or len(llm_results) != 1:
                    continue
                ordinary_result = ordinary_results[0]
                llm_result = llm_results[0]
                duration_delta = None
                if ordinary_result.duration_ms is not None and llm_result.duration_ms is not None:
                    duration_delta = llm_result.duration_ms - ordinary_result.duration_ms
                matched_pairs.append({
                    "input_sha256": digest,
                    "ordinary_input_id": ordinary_case.input_id,
                    "llm_input_id": llm_case.input_id,
                    "ordinary_status": ordinary_result.status,
                    "llm_status": llm_result.status,
                    "ordinary_http_status": ordinary_result.http_status,
                    "llm_http_status": llm_result.http_status,
                    "ordinary_duration_ms": ordinary_result.duration_ms,
                    "llm_duration_ms": llm_result.duration_ms,
                    "llm_minus_ordinary_duration_ms": duration_delta,
                })

    model_summaries: dict[str, dict[str, Any]] = {}
    trial_summaries: dict[str, dict[str, Any]] = {}
    for case in input_cases:
        if case.input_source != "llm_suggested":
            continue
        model = case.generator_model or "unspecified"
        model_row = model_summaries.setdefault(model, {
            "input_count": 0,
            "outcome_count": 0,
            "status_counts": {status: 0 for status in ("accepted", "rejected", "error", "timeout", "crash")},
            "durations_ms": [],
            "trial_groups": set(),
        })
        model_row["input_count"] += 1
        group = case.trial_group or case.input_id
        model_row["trial_groups"].add(group)
        for outcome in outcomes_by_input.get(case.input_id, []):
            model_row["outcome_count"] += 1
            model_row["status_counts"][outcome.status] += 1
            if outcome.duration_ms is not None:
                model_row["durations_ms"].append(float(outcome.duration_ms))
            trial_row = trial_summaries.setdefault(group, {
                "model": model,
                "input_count": 0,
                "replicate_indices": [],
                "outcome_count": 0,
                "status_counts": {status: 0 for status in ("accepted", "rejected", "error", "timeout", "crash")},
                "durations_ms": [],
            })
            trial_row["input_count"] += 1
            if case.replicate_index is not None:
                trial_row["replicate_indices"].append(case.replicate_index)
            trial_row["outcome_count"] += 1
            trial_row["status_counts"][outcome.status] += 1
            if outcome.duration_ms is not None:
                trial_row["durations_ms"].append(float(outcome.duration_ms))

    def finish_summary(row: dict[str, Any]) -> dict[str, Any]:
        durations = row.pop("durations_ms")
        if "trial_groups" in row:
            row["trial_group_count"] = len(row.pop("trial_groups"))
        if "replicate_indices" in row:
            row["replicate_indices"] = sorted(row["replicate_indices"])
        row["mean_duration_ms"] = float(statistics.mean(durations)) if durations else None
        row["median_duration_ms"] = float(statistics.median(durations)) if durations else None
        return row

    return {
        **summaries,
        "matched_by_sha256": matched_pairs,
        "llm_by_model": {model: finish_summary(row) for model, row in sorted(model_summaries.items())},
        "llm_by_trial_group": {group: finish_summary(row) for group, row in sorted(trial_summaries.items())},
    }


def features_for_runs(feature_builder: Any, run_ids: Sequence[str]) -> dict[str, dict[str, float]]:
    """Build a label-free numeric feature view for selected NWDAF run IDs."""
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("run_ids must be unique")
    features_by_run: dict[str, dict[str, float]] = {}
    for run_id in run_ids:
        raw_features = feature_builder.build_features_for_run(run_id)
        projected: dict[str, float] = {}
        for name in FEATURE_NAMES:
            value = raw_features.get(name, 0.0)
            try:
                numeric_value = float(value or 0.0)
            except (TypeError, ValueError) as error:
                raise ValueError(f"feature {name} for {run_id} is not numeric") from error
            if not np.isfinite(numeric_value):
                raise ValueError(f"feature {name} for {run_id} must be finite")
            projected[name] = numeric_value
        features_by_run[run_id] = projected
    return features_by_run


def evaluate_run_detection(
    features_by_run: Mapping[str, Mapping[str, float]],
    labels: Sequence[RunLabel],
    *,
    feature_names: Sequence[str] = FEATURE_NAMES,
) -> dict[str, Any]:
    """Train on labeled training runs and evaluate once on held-out runs.

    This probes whether run-level telemetry separates input-test runs from
    normal runs. It is not the existing security-anomaly model or a
    vulnerability classifier.
    """
    labels_by_run = {item.run_id: item for item in labels}
    if len(labels_by_run) != len(labels):
        raise ValueError("run labels must have unique run_id values")
    if set(features_by_run) != set(labels_by_run):
        raise ValueError("feature rows and run labels must cover the same run IDs")

    train_ids = sorted(run_id for run_id, item in labels_by_run.items() if item.split == "train")
    held_out_ids = sorted(run_id for run_id, item in labels_by_run.items() if item.split == "held_out")
    if not train_ids or not held_out_ids:
        raise ValueError("both train and held_out runs are required")
    if any(item.label not in {"normal", "input_test"} for item in labels):
        raise ValueError("labels must be normal or input_test")

    def matrix(run_ids: list[str]) -> np.ndarray:
        rows = []
        for run_id in run_ids:
            run_features = features_by_run[run_id]
            row = []
            for name in feature_names:
                try:
                    value = float(run_features.get(name, 0.0))
                except (TypeError, ValueError) as error:
                    raise ValueError(f"feature {name} for {run_id} is not numeric") from error
                if not np.isfinite(value):
                    raise ValueError(f"feature {name} for {run_id} must be finite")
                row.append(value)
            rows.append(row)
        return np.asarray(rows, dtype=float)

    train_y = np.asarray([labels_by_run[run_id].label for run_id in train_ids])
    held_out_y = np.asarray([labels_by_run[run_id].label for run_id in held_out_ids])
    if set(train_y) != {"normal", "input_test"} or set(held_out_y) != {"normal", "input_test"}:
        raise ValueError("train and held_out must each contain both classes")

    model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42)
    model.fit(matrix(train_ids), train_y)
    held_out_matrix = matrix(held_out_ids)
    predictions = model.predict(held_out_matrix)
    probabilities = model.predict_proba(held_out_matrix)
    input_test_column = list(model.classes_).index("input_test")
    tn, fp, fn, tp = confusion_matrix(
        held_out_y,
        predictions,
        labels=["normal", "input_test"],
    ).ravel()

    return {
        "model": "random_forest_input_test_probe",
        "feature_schema": "nwdaf-run-features-v1",
        "train_run_ids": train_ids,
        "held_out_run_ids": held_out_ids,
        "feature_names": list(feature_names),
        "metrics": {
            "run_count": len(held_out_ids),
            "precision": float(precision_score(held_out_y, predictions, pos_label="input_test", zero_division=0)),
            "recall": float(recall_score(held_out_y, predictions, pos_label="input_test", zero_division=0)),
            "f1": float(f1_score(held_out_y, predictions, pos_label="input_test", zero_division=0)),
            "roc_auc": float(roc_auc_score(held_out_y == "input_test", probabilities[:, input_test_column])),
            "false_positive_rate": float(fp / (fp + tn)) if fp + tn else 0.0,
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
    }