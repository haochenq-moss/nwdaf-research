# Offline Configurations

The evaluator in `scripts/evaluate_configurations.py` compares:

- **B0**: conventional Linux load threshold, selected on validation data.
- **B1**: Random Forest on verified Linux telemetry features.
- **B2**: B1 with the policy confidence gate and mitigation eligibility count.

The feature builder now consumes real `sbi/events.jsonl`, `pfcp/events.jsonl`,
`free5gc/events.jsonl`, and Linux eBPF streams when present. It records explicit
availability flags and never treats an empty collector file as observed traffic.

All configurations preserve the supplied whole-run train/validation/test split.
The test set is used only for the final report. Ground-truth fields are removed
from the feature matrix; this is tested to prevent label leakage.

The evaluator also reports average precision, ROC-AUC, Brier score, and a
bootstrap 95% interval for B1 F1. The Random Forest `predict_proba` output is
reported as a probability estimate; it is not called calibrated unless a
separate calibration procedure is measured.

## Advanced Evaluation

The advanced supplemental evaluator is written to
`evaluation/advanced_supplemental_test30.json`. It uses a separate
scenario-stratified split with 72 train, 16 validation, and 32 test runs. The
advanced path adds train-only `StandardScaler` normalization, validation-based
Random Forest hyperparameter and class-weight selection, three random seeds
(`7`, `42`, and `123`), and sigmoid probability calibration. All three seeds
achieved precision, recall, F1, and average precision of 1.0000 on this
controlled supplemental test split; Brier scores were 0.00326, 0.00264, and
0.00279 respectively. These results remain supplemental and controlled rather
than production generalization evidence.

The CUDA MLP backend supports validation early stopping and class-weighted loss.
`models/temporal_gru.py` provides an optional GRU over real Linux event
sequences; its results must only be reported after a CUDA Slurm run produces a
recorded `device: cuda` artifact.

Current pilot test results:

| Configuration | Precision | Recall | F1 | False-positive rate |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.8889 | 0.8889 | 0.8889 | 1.0000 |
| B1 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |
| B2 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |

These are measured on 10 held-out runs. B2 response latency, recovery time,
availability, throughput, and packet-loss changes are unavailable in the
offline archive and are not fabricated.

## Supplemental Network-Feature Campaigns

The formal supplemental campaign contains 120 additional runs: 30 NORMAL, 30
S08, 30 S10, and 30 S14. It contains 8,034 real SBI events and 181 real PFCP
events. The scenario-stratified whole-run split is 84 train, 16 validation, and
20 test runs.

The separate multi-load campaign contains 80 runs across L1 and L2: 20 runs per
scenario for NORMAL, S08, S10, and S14. It contains 3,684 SBI events and 156
PFCP events. These datasets are not merged into the immutable pilot score.

The evaluator in `scripts/evaluate_supplemental_network.py` compares network-only
features with a combined Linux/network feature set while preserving complete-run
splits. The results validate network telemetry availability and feature direction
in controlled campaigns; they are not production generalization claims.