# Project Method and Results Summary

## 1. Project Scope

This project implements an external **NWDAF-like Security Analytics Prototype** for detecting and responding to Linux-based attacks in an open-source 5G Core environment. It is not presented as a fully 3GPP-compliant NWDAF and does not modify the free5GC source code.

The system follows a two-machine architecture:

- **Ubuntu free5GC testbed:** free5GC network functions, free-ran-ue, UE PDU sessions, Linux/process telemetry, SBI and PFCP logs, and controlled security scenarios.
- **GPU analytics server:** immutable dataset ingestion, feature extraction, model training and inference, NWDAF-like APIs, policy validation, response adapters, audit logging, and verification.

The main processing path is:

```text
Telemetry collection
  -> run association and feature extraction
  -> model inference
  -> policy validation
  -> bounded response
  -> verification and audit
```

The model produces an evidence-backed diagnosis and never executes arbitrary commands. A separate policy layer validates action type, target NF, confidence, duration, and authorization before a response agent can act.

## 2. Dataset and Feature Method

The immutable pilot dataset contains 90 valid runs with 10 scenarios, three traffic loads, and a whole-run split of 60 training, 20 validation, and 10 test runs. The main pilot model uses verified Linux host/process telemetry, memory and load features, run metadata, and ground-truth labels only for evaluation.

The feature pipeline also supports real network telemetry streams when present:

- `sbi/events.jsonl`
- `pfcp/events.jsonl`
- `free5gc/events.jsonl`
- Linux eBPF event streams

Empty collector files are explicitly marked unavailable and are never replaced with fabricated values.

A separate supplemental campaign was generated on the real Ubuntu/free5GC testbed to provide network-layer evidence. It contains 120 runs distributed across NORMAL, S08, S10, and S14 scenarios, with 8,034 real SBI events and 181 PFCP events. A second multi-load campaign contains 80 runs across L1 and L2 load profiles.

All model splits are performed at the complete-run level rather than at the individual-event level to avoid train/test leakage.

## 3. Model and Configuration Method

Three configurations are evaluated:

- **B0:** conventional Linux load-threshold baseline.
- **B1:** Random Forest security detector using telemetry features.
- **B2:** B1 combined with a policy-bounded response layer.

The response layer supports authenticated and allow-listed actions including operator alerting and a bounded reversible traffic-rate-limit action. The Ubuntu response-agent uses API-key authentication, persistent replay protection, SQLite state, JSONL audit records, and automatic restoration of the original `fq_codel` queue discipline after a bounded rate-limit duration.

## 4. Frozen Pilot Results

On the 10-run held-out pilot test set:

| Configuration | Precision | Recall | F1 | False-positive rate |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.8889 | 0.8889 | 0.8889 | 1.0000 |
| B1 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |
| B2 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |

For B1 and B2, the confusion matrix is:

```text
TN = 1
FP = 0
FN = 1
TP = 8
```

Thus, the detector correctly identified eight of nine attack-positive test runs and all normal test runs, with no false positives.

## 5. Live B0/B1 Results

Ten live trials were executed over the real `ueTun0` path to the Ubuntu host. The measured results were:

| Metric | B0 | B1 |
| --- | ---: | ---: |
| RTT mean | 0.0486 +/- 0.0084 ms | 0.0749 +/- 0.0600 ms |
| Packet loss | 0% | 0% |
| Throughput sent | 9.918 +/- 3.260 Gbps | 11.131 +/- 2.667 Gbps |
| Throughput received | 9.665 +/- 3.172 Gbps | 10.882 +/- 2.616 Gbps |
| Detection latency | not applicable | 17.52 +/- 0.69 ms |

Throughput was measured on the local UE-tunnel-to-Ubuntu-host path rather than an external Internet path. The trials were sequential or randomized-order live measurements and therefore do not establish that the analytics model caused a network-performance improvement.

## 6. Supplemental SBI/PFCP Results

The 120-run supplemental campaign contains:

```text
NORMAL = 30
S08 = 30
S10 = 30
S14 = 30
SBI events = 8034
PFCP events = 181
Train/validation/test = 84/16/20
```

The network-feature ablation produced:

| Feature set | Accuracy | Macro F1 | Test samples |
| --- | ---: | ---: | ---: |
| SBI/PFCP only | 1.0000 | 1.0000 | 20 |
| Linux + SBI/PFCP | 1.0000 | 1.0000 | 20 |

These results demonstrate that real SBI/PFCP telemetry can be collected, transferred, parsed, and used by the analytics pipeline. Because the campaign uses four controlled scenario classes and limited load conditions, the result is supplemental exploratory evidence rather than a production generalization claim.

The additional L1/L2 multi-load campaign contains 80 runs and produced the following configuration results:

| Configuration | Precision | Recall | F1 | False-positive rate |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.6667 | 0.6667 | 0.6667 | 1.0000 |
| B1 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |
| B2 | 1.0000 | 0.8889 | 0.9412 | 0.0000 |

Per-load B1 F1 was 1.0000 for L1 and 0.9231 for L2.

## 7. B2 Response Validation

A real alert-only B2 trial measured:

```text
Prediction: ANOMALY
Probability: 0.885
Detection latency: 20.56 ms
Response latency: 24.89 ms
```

Ten controlled rate-limit trials were also executed:

```text
10/10 requests accepted
10/10 rate-limit actions applied
10/10 trials restored to fq_codel
Packet loss: 0% in all trials
Mean RTT: approximately 0.0583 ms
```

The observed qdisc transition was:

```text
fq_codel -> tbf, 1 Mbit -> fq_codel
```

These trials validate the implementation path, bounded enforcement, automatic restoration, and auditability. They do not by themselves establish causal service recovery or production-scale mitigation effectiveness.

## 8. Reproducibility and Evidence Files

Important project artifacts include:

- Frozen pilot archive: `data/pilot_raw.tar.gz`
- Pilot split: `data/raw/split_manifest.json`
- Pilot configuration results: `evaluation/configurations.json`
- Live B0/B1 summary: `evaluation/configuration_trials_summary.json`
- Supplemental telemetry summary: `evaluation/supplemental_large_telemetry.json`
- Supplemental network ablation: `evaluation/supplemental_large_network_ablation.json`
- Multi-load configuration results: `evaluation/supplemental_multiload_configurations.json`
- B2 alert trial: `evaluation/b2_alert_trial.json`
- Repeated B2 rate-limit evidence: `evaluation/b2_rate_trials.jsonl`
- Model artifact: `models/rf-v1/model.pkl`
- Model provenance: `models/rf-v1/manifest.json`
- Paper-oriented report: `docs/paper_results.md`

The latest project test suite contains 52 passing tests.

## 9. Limitations

The current evaluation has several limitations:

- The original pilot model is primarily Linux/process telemetry based.
- The supplemental network campaign uses controlled scenario generators and limited load conditions.
- Live B0/B1 measurements are not a randomized carrier-scale experiment.
- The B2 rate-limit experiment is controlled and bounded rather than a full attack-recovery campaign.
- Causal recovery, availability improvement, and production generalization have not been established.
- The Ubuntu user still has broader sudo privileges than the response-agent allow-list, which remains a residual least-privilege risk.
- Full Kubernetes quarantine, OVS enforcement, clean NF replacement, UPF failover, and full 3GPP NWDAF compliance are future work rather than demonstrated capabilities.
