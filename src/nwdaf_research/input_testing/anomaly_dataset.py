from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score, roc_auc_score

from nwdaf_research.input_testing.protocol_evidence import inspect_case_evidence
from nwdaf_research.live.telemetry_window import BASELINE_CONTRACT, CollectorHealth, TelemetryWindow, parse_time


LABELS = {"normal", "expected_rejection", "anomalous"}
FEATURES = TelemetryWindow("2026-01-01T00:00:00Z", contract=BASELINE_CONTRACT).feature_names


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _reference(root: Path, reference: dict[str, Any]) -> Path:
    relative = reference["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("unsafe evidence path")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("evidence path escapes bundle or is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != reference["sha256"]:
        raise ValueError("evidence hash mismatch")
    return path


def _window_features(root: Path, manifest: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, float]:
    if telemetry.get("contract") != BASELINE_CONTRACT:
        raise ValueError("telemetry contract must be linux-sbi-pfcp-v1")
    reference = telemetry.get("snapshots_ref")
    if not isinstance(reference, dict) or reference not in telemetry["evidence_refs"]:
        raise ValueError("snapshots_ref must be a hash-bound supporting artifact")
    start, end = parse_time(telemetry["window_start"]), parse_time(telemetry["window_end"])
    window = TelemetryWindow(start, duration_sec=(end - start).total_seconds(), contract=BASELINE_CONTRACT)
    stream_path = _reference(root, reference)
    for line in stream_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("run_id") != manifest["run_id"] or row.get("input_sha256") != manifest["input"]["sha256"]:
            raise ValueError("snapshot case/run identity mismatch")
        if row["type"] == "snapshot":
            collectors = {
                source: CollectorHealth(parse_time(health["heartbeat_at"]), health["collector_healthy"],
                                        health["telemetry_source_synced"], parse_time(health["observed_through"]))
                for source, health in row["collectors"].items()
            }
            window.add_snapshot(row["observed_at"], counters=row["counters"],
                                linux_sample=row["linux_sample"], collectors=collectors)
        elif row["type"] == "seal":
            if window.is_sealed():
                raise ValueError("duplicate window seal")
            window.seal(row["observed_at"])
        else:
            raise ValueError("unsupported snapshot record")
    result = window.inspect(end)
    if result["status"] != "READY" or set(result["features"]) != set(FEATURES):
        raise ValueError(f"telemetry window not ready: {result['status']}")
    return result["features"]


def load_anomaly_dataset(dataset_path: str | Path, plan_path: str | Path, *, allow_simulation: bool = False) -> dict[str, Any]:
    """Verify externally collected runs and labels before any model fitting."""
    dataset_path, plan_path = Path(dataset_path).resolve(), Path(plan_path).resolve()
    dataset_bytes, plan_bytes = dataset_path.read_bytes(), plan_path.read_bytes()
    dataset, plan = json.loads(dataset_bytes), json.loads(plan_bytes)
    simulated = dataset.get("simulation_only") is True
    if simulated and allow_simulation is not True:
        raise ValueError("simulation dataset requires explicit allow_simulation=True")
    if simulated != (plan.get("simulation_only") is True):
        raise ValueError("dataset and plan simulation flags must match")
    if plan.get("schema_version") != "fuzz-anomaly-analysis-plan-v1":
        raise ValueError("explicit fuzz-anomaly analysis plan required")
    if plan.get("contract") != BASELINE_CONTRACT or plan.get("feature_names") != list(FEATURES):
        raise ValueError("plan feature contract mismatch")
    if plan.get("model") != "random_forest_200_seed42" or plan.get("threshold") != 0.5:
        raise ValueError("this baseline requires the explicit fixed model and threshold")
    if plan.get("collection_semantics") != "observation_time_cursor_reads_excluding_preexisting_history":
        raise ValueError("plan must declare evaluated collection semantics")
    frozen_at = parse_time(plan["frozen_at"])
    if plan.get("frozen") is not True:
        raise ValueError("analysis plan must be explicitly frozen before evaluation")
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    if dataset.get("schema_version") != "fuzz-anomaly-dataset-v1" or dataset.get("analysis_plan_sha256") != plan_hash:
        raise ValueError("dataset must bind the exact frozen analysis plan")
    entries = dataset.get("runs")
    if not isinstance(entries, list) or not entries:
        raise ValueError("no independently collected and reviewed runs supplied")
    rows, groups, run_ids, commits, intervals = [], {}, set(), set(), []
    for entry in entries:
        relative = entry["bundle_path"]
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("bundle_path must be relative to dataset directory")
        root = (dataset_path.parent / relative).resolve()
        if not root.is_relative_to(dataset_path.parent):
            raise ValueError("bundle escapes dataset directory")
        if inspect_case_evidence(root)["evidence_chain_status"] != "REFERENCES_COMPLETE":
            raise ValueError(f"incomplete case evidence: {relative}")
        manifest = _json(root / "case_evidence.json")
        review = _json(_reference(root, manifest["stages"]["analyst_decision"]))
        telemetry = _json(_reference(root, manifest["stages"]["telemetry_bundle"]))
        label = review.get("outcome_label")
        if simulated:
            if manifest.get("simulation_only") is not True or review.get("simulation_only") is not True or review.get("label_basis") != "synthetic_generator_scenario" or review.get("independence_declared") is not False:
                raise ValueError("explicit synthetic scenario label required without independent-review claims")
        elif label not in LABELS or review.get("independence_declared") is not True or review.get("label_basis") != "independent_observed_behavior":
            raise ValueError("external independent outcome label required; exposure/model labels are prohibited")
        if label not in LABELS:
            raise ValueError("unsupported outcome label")
        if telemetry.get("collection_semantics") != plan["collection_semantics"]:
            raise ValueError("collection semantics mismatch")
        domain = telemetry.get("clock_domain")
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("explicit telemetry host/boot clock domain required")
        split = entry.get("split")
        if split not in {"train", "held_out"}:
            raise ValueError("split must be train or held_out")
        if split == "train" and parse_time(telemetry["window_end"]) > frozen_at:
            raise ValueError("training observations must precede plan freeze")
        if split == "held_out" and (
            entry.get("unseen_declared") is not True or parse_time(telemetry["window_start"]) <= frozen_at
        ):
            raise ValueError("held-out data must be declared unseen and newly collected after plan freeze")
        interval = (domain, parse_time(telemetry["window_start"]), parse_time(telemetry["window_end"]), split)
        for old_domain, old_start, old_end, old_split in intervals:
            if domain == old_domain and split != old_split and interval[1] < old_end and old_start < interval[2]:
                raise ValueError("overlapping telemetry activity across partitions")
        intervals.append(interval)
        run_id = manifest["run_id"]
        if run_id in run_ids:
            raise ValueError("complete runs cannot be duplicated or split")
        run_ids.add(run_id)
        for field in ("input_family", "episode_group"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"explicit {field} required")
        for identity in (("family", entry["input_family"]), ("episode", entry["episode_group"]),
                         ("bytes", manifest["input"]["sha256"])):
            groups.setdefault(identity, set()).add(split)
            if len(groups[identity]) > 1:
                raise ValueError(f"cross-split leakage: {identity[0]}")
        commits.add(manifest["free5gc_commit"])
        rows.append({"run_id": run_id, "split": split, "label": label,
                     "input_family": entry["input_family"], "episode_group": entry["episode_group"],
                     "input_sha256": manifest["input"]["sha256"],
                     "features": _window_features(root, manifest, telemetry),
                     "manifest_sha256": hashlib.sha256((root / "case_evidence.json").read_bytes()).hexdigest(),
                     "review_sha256": manifest["stages"]["analyst_decision"]["sha256"]})
    if len(commits) != 1:
        raise ValueError("target revisions require separate evaluations")
    for split in ("train", "held_out"):
        if {row["label"] for row in rows if row["split"] == split} != LABELS:
            raise ValueError("train and held_out must each include normal, expected_rejection and anomalous")
    return {"rows": rows, "simulation_only": simulated, "plan_sha256": plan_hash, "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
            "free5gc_commit": next(iter(commits))}


def evaluate_anomaly_dataset(dataset_path: str | Path, plan_path: str | Path, *, allow_simulation: bool = False) -> dict[str, Any]:
    verified = load_anomaly_dataset(dataset_path, plan_path, allow_simulation=allow_simulation)
    rows = verified["rows"]
    train = [row for row in rows if row["split"] == "train"]
    held = [row for row in rows if row["split"] == "held_out"]
    def matrix(items):
        return np.asarray([[row["features"][name] for name in FEATURES] for row in items], dtype=float)
    model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")
    model.fit(matrix(train), [int(row["label"] == "anomalous") for row in train])
    probability = model.predict_proba(matrix(held))[:, list(model.classes_).index(1)]
    predictions = (probability >= 0.5).astype(int)
    truth = np.asarray([int(row["label"] == "anomalous") for row in held])
    tn, fp, fn, tp = confusion_matrix(truth, predictions, labels=[0, 1]).ravel()
    control_rates = {}
    for label in ("normal", "expected_rejection"):
        indices = [index for index, row in enumerate(held) if row["label"] == label]
        control_rates[label] = {"run_count": len(indices), "false_positive_rate": float(np.mean(predictions[indices]))}
    return {
        "schema_version": "fuzz-anomaly-evaluation-v1", "contract": BASELINE_CONTRACT,
        "simulation_only": verified["simulation_only"], "research_result": not verified["simulation_only"],
        "model_fitted": True, "offline_predictions_performed": True, "live_inference_performed": False,
        "feature_names": list(FEATURES), "model": "random_forest_200_seed42", "threshold": 0.5,
        "analysis_plan_sha256": verified["plan_sha256"], "dataset_sha256": verified["dataset_sha256"],
        "free5gc_commit": verified["free5gc_commit"], "training_run_count": len(train),
        "held_out_run_count": len(held), "metrics": {
            "precision": float(precision_score(truth, predictions, zero_division=0)),
            "recall": float(recall_score(truth, predictions, zero_division=0)),
            "f1": float(f1_score(truth, predictions, zero_division=0)),
            "roc_auc": float(roc_auc_score(truth, probability)), "false_positive_rate": float(fp / (fp + tn)),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }, "control_metrics": control_rates,
        "held_out_predictions": [{"run_id": row["run_id"], "observed_label": row["label"],
                                  "anomaly_probability": float(score), "predicted_anomalous": bool(prediction)}
                                 for row, score, prediction in zip(held, probability, predictions)],
        "run_provenance": [{key: value for key, value in row.items() if key != "features"} for row in rows],
        "model_deployment_approved": False, "actionable": False, "reviewer_independence_authenticated": False,
        "limitations": (
            "SIMULATION ONLY: generated scenarios, mock approvals and virtual timestamps; metrics do not demonstrate live detection or fuzz causality. No live actions are authorized."
            if verified["simulation_only"] else
            "Declared external review is not authenticated; timing/exposure association is not proof of fuzz causality. Small datasets are exploratory; no live actions or mitigation are authorized."
        ),
    }