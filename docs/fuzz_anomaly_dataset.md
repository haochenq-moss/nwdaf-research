# Fuzz-Linked Telemetry Dataset and Evaluation

## Implemented Scope

`input_testing/anomaly_dataset.py` and `scripts/evaluate_fuzz_anomalies.py`
implement the defensive analysis side for **externally collected** case bundles.
They do not reproduce failures, deliver NAS inputs, contact the testbed, perform
mitigation, or approve a deployed model. No additional NRF collection is needed.

The current `RNAS0001` case has no same-run Linux/SBI/PFCP bundle and no reviewed
anomaly label. Historical benign NRF results are already inspected and have no
reviewed anomalous condition. Neither is a valid training/evaluation dataset
for this workflow. Real model fitting and detection metrics remain blocked.

## Case and Feature Validation

Each bundle follows the [case evidence contract](fuzz_case_evidence_check.md).
Input, observed outcomes, reviews, and telemetry must share the exact input
hash, run ID, and pinned free5GC revision. Hash-bound supporting artifacts and
protocol/cleanup/analyst review records must pass reference validation.

The `telemetry_bundle` stage additionally supplies:

- `contract`: `linux-sbi-pfcp-v1`.
- `collection_semantics`: `observation_time_cursor_reads_excluding_preexisting_history`.
- `clock_domain`: explicit host/boot clock identity.
- `snapshots_ref`: relative path/SHA-256, also included in `evidence_refs`.
- `window_start` and `window_end` bracketing the case observation.

The snapshots artifact contains health-bearing snapshot JSONL and one seal, as
in the [window contract](telemetry_windows.md). Each snapshot and seal repeats
`run_id` and `input_sha256`. The analyzer recomputes the sixteen features from
actual samples and cumulative counters; supplied precomputed vectors are not
used. Missing collectors, invalid values, counter decreases, missing boundaries,
or inadequate sampling block fitting. Healthy sources can have zero events.

## Independent Outcome Labels

The external `analyst_decision` stage must include `decision: approved`,
`outcome_label`, `label_basis: independent_observed_behavior`, and
`independence_declared: true`, with reviewer/time/rationale and supporting
evidence required by the case checker. Allowed outcome labels are:

| Label | Binary Model Class |
| --- | --- |
| `normal` | Non-anomalous control |
| `expected_rejection` | Non-anomalous rejection control |
| `anomalous` | Independently observed anomalous effect |

`input_test`, seed source, or a model score cannot supply ground truth.
Reviewer identity and independence are assertions requiring external assurance;
these programs do not authenticate people or validate the scientific conclusions.
An anomaly label does not by itself establish fuzz causality or a vulnerability.

## Frozen Analysis Plan

Provide a JSON plan with schema `fuzz-anomaly-analysis-plan-v1`,
`contract: linux-sbi-pfcp-v1`, `frozen: true`, actual timezone-aware `frozen_at`,
the collection semantics above, `model: random_forest_200_seed42`,
`threshold: 0.5`, and `feature_names` in this exact order:

```json
[
  "duration_sec", "linux_load_1m_mean", "linux_load_1m_std",
  "linux_load_1m_min", "linux_load_1m_max", "linux_memory_total_mean",
  "linux_memory_available_mean", "memory_available_ratio_mean",
  "linux_event_count", "sbi_event_count", "sbi_error_event_count",
  "pfcp_event_count", "pfcp_request_count", "pfcp_response_count",
  "sbi_telemetry_available", "pfcp_telemetry_available"
]
```

Write and preserve the plan before collecting fresh held-out runs. Do not
backdate the freeze or declare already-inspected data unseen. There is no plan
automatically approving the existing historical model.

## Dataset Manifest

The dataset JSON has schema `fuzz-anomaly-dataset-v1`,
`analysis_plan_sha256` binding the exact plan file, and a nonempty `runs` list.
Each entry provides relative `bundle_path`, `split` (`train` or `held_out`),
`input_family`, `episode_group`, and `unseen_declared` for held-out observations.

Both partitions require all three independently reviewed labels. Training
observations must finish before plan freeze; held-out observations must begin
after it and be declared unseen. Duplicate complete runs, exact bytes, input
families, or correlated episode groups cannot cross partitions. Overlapping
activity within the same clock domain cannot cross partitions either. One target
revision is evaluated at a time; revisions cannot be silently pooled.

## Execute

First validate real data without fitting:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_fuzz_anomalies.py \
  --dataset /path/to/dataset.json \
  --analysis-plan /path/to/frozen-plan.json \
  --output evaluation/<new-preflight-report>.json
```

Add `--fit` only after preflight succeeds. The fixed Random Forest uses 200
trees, seed 42 and balanced class weights, fitting only training runs. Its
threshold is fixed at 0.5; held-out labels are used only for evaluation, not
training, tuning, or assigning ground truth.

Results include confusion matrix, false-positive rate, precision, recall, F1,
ROC AUC, and separate false-positive rates for normal and expected-rejection
controls. Provenance and reviewed labels stay traceable to every prediction.
Existing result files are never overwritten. No model is deployed or serialized
for live use by this command. Fit/evaluation readiness is not model approval.

Insufficient or invalid evidence produces a `BLOCKED` report and nonzero exit;
it never produces invented metrics. Tests use synthetic non-NAS fixtures and
exercise real estimator fitting, but their scores are software verification,
not research results. Small real datasets remain exploratory, and declaring
fuzz-triggered detection requires independently supported exposure/effect
association and suitable controls beyond these structural checks.