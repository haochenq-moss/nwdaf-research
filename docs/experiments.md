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

Current pilot test results:

| Configuration | Precision | Recall | F1 | False-positive rate |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.8889 | 0.8889 | 0.8889 | 1.0000 |
| B1 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |
| B2 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |

These are measured on 10 held-out runs. B2 response latency, recovery time,
availability, throughput, and packet-loss changes are unavailable in the
offline archive and are not fabricated.

## Supplemental Network-Feature Campaign

The separate Ubuntu campaign contains 12 additional runs: 3 NORMAL, 3 S08,
3 S10, and 3 S14. It contains 652 real SBI events and 17 real PFCP events.
The exploratory evaluator in `scripts/evaluate_supplemental_network.py` holds
one complete run out per scenario and compares network-only features with a
combined Linux/network feature set. These results must not be merged into the
frozen pilot test score; the campaign is small and exists to validate telemetry
availability and feature direction before a larger repetition matrix.