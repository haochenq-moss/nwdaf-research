# Held-Out Benign Observability Results

## Authorized Descriptive Unblinding

After pilot completion, the user requested continuation of the proposed scoped
descriptive unblinding step. The separate
[authorization](../evaluation/descriptive_unblinding_authorization_20261003.json)
binds the analysis lock SHA-256
`adac2105bb165e33551150aee14f5506bd5d26ac023b4cf444638cddd25fb8f5`.
Training, inference, threshold selection, and mitigation remain disabled.
The lock was written after pilot inspection and held-out acquisition but before
held-out outcome inspection; this is not full pre-collection preregistration.

The outcomes are now **unblinded**. Do not reuse these same eight pairs as a
fresh unseen evaluation after changing analysis or model choices. No live
testbed operation was performed for this analysis; acquisition artifacts and
declared labels were not modified.

## Primary Endpoint

The analyzer recomputed windows and operation synchronization from sanitized
raw captures, checked saved vectors/streams/journals, verified frozen order and
fixture matching, and checked stored deltas. All eight planned held-out pairs
passed automated integrity validation; zero invalid pairs were reported.

| Pair | Middle-Window SBI Difference (Benign Minus Passive) |
| --- | ---: |
| 5 | +2 |
| 6 | +2 |
| 7 | +2 |
| 8 | +2 |
| 9 | +2 |
| 10 | +2 |
| 11 | +2 |
| 12 | +2 |

Median: **2**; minimum/maximum: **2/2**; positive/zero/negative: **8/0/0**.
This is consistent with the known token POST plus fixed discovery GET being
observed by the log-derived SBI collector. It demonstrates repeatable benign
signaling observability in this testbed, not detection of attacks, suspicious
NAS behavior, or software vulnerabilities. No hypothesis test was performed.

## Predefined Secondary Descriptions

The 48 held-out windows contain sixteen baseline features each. The windows
are correlated within matched blocks and pairs; the primary unit remains eight
pairs, not 48 independent samples.

- Actual window durations: **9.972285-10.019030 seconds**.
- Total observed SBI error events: **0**; this is not a detector false-positive rate.
- PFCP counts: **1-3 events per window**, with no causal attribution to NRF.
- Mean Linux load per window: **0.266-1.722**.
- Mean available-memory ratios per window: **0.287060-0.312918**.
- All eight pairs belong to one recorded collector/control/parser-hash stratum.

Detailed vectors, operation receipts, implementation strata, artifact hashes,
and pair endpoints are preserved in
[benign_held_out_descriptive_20261003.json](../evaluation/benign_held_out_descriptive_20261003.json).
File hashes check identity/consistency, not source authenticity or complete
loaded-code attestation. Health watermarks describe completed observation-time
reads, not packet/kernel event-time completeness. Parser coverage of all possible
log formats was not established. Independent analyst review remains pending.

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python scripts/analyze_benign_held_out.py \
  --root data/input_testing \
  --analysis-lock configs/benign_control_analysis_lock_v1.json \
  --authorization evaluation/descriptive_unblinding_authorization_20261003.json \
  --output evaluation/<new-descriptive-report>.json
```

Existing outputs are refused. Missing or inconsistent pairs are retained with
null endpoints rather than zeroes; summaries report the valid count and all
planned failures. This CLI has no model, network-stimulus, or response flags.
Independent review must not be replaced by an automated `VERIFIED` result.

## Goal Boundary

The benign-control campaign has connected controlled signaling, real telemetry,
timing receipts, provenance, grouped analysis, and pending analyst evidence.
It has not connected a reproduced software finding to a controlled network
outcome, measured fuzz-triggered detection, trained a suitable anomaly model,
or evaluated authorized mitigation/rollback. Those remain separate research
milestones, and additional independent data would be required to evaluate a
new model without reusing these already inspected held-out pairs.