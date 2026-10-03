# Scoped Held-Out Collection Authorization

The user explicitly permitted the scoped next step after being told that model
validation and network mitigation require separate evidence and action bounds.
[scoped_live_authorization_20261003.json](../evaluation/scoped_live_authorization_20261003.json)
records authorization for frozen-plan benign collection of pairs 5-12, with
inference/model deployment/network enforcement disabled. The response scope is
operator-alert-only on explicit operator request; no alert has been delivered.

The earlier user-edited
[operator approval](../evaluation/analyst_review_pair02_20261003/operator_approval.json)
was preserved unchanged. Its boolean assertions do not supply independent
review evidence, model compatibility, scientific validation, or a bounded
network-enforcement action. The runner does not consume that broad record as
an execution capability. It requires the scoped authorization, matching frozen
plan hash, permitted pair ID, and registered AMF identity before acquisition.

## Actual Execution

**All held-out pairs 5-12** have executed under this permission, per the
unchanged frozen schedule. Both collection blocks in every pair returned
`READY`; no inference or mitigation ran. Event counts, feature distributions,
request timing results, and paired deltas were not inspected during acquisition.
The CLI withholds those values for held-out pairs while preserving raw evidence
and receipts for later analysis.

| Pair | Execution Order | Passive Status | Benign NRF Status |
| --- | --- | --- | --- |
| 5 | Passive, benign NRF | READY | READY |
| 6 | Benign NRF, passive | READY | READY |
| 7 | Passive, benign NRF | READY | READY |
| 8 | Benign NRF, passive | READY | READY |
| 9 | Benign NRF, passive | READY | READY |
| 10 | Passive, benign NRF | READY | READY |
| 11 | Benign NRF, passive | READY | READY |
| 12 | Passive, benign NRF | READY | READY |

Evidence directories follow
`data/input_testing/benign-control-held-out-pair<two-digit-id>-20261003/`.
All eight pair journals bind authorization SHA-256
`2888669784517a47fc74fd24ab1c1094fc6150f9d9748ae46b29896cb6b995c8`.
This is controlled-access procedural blinding, not encryption: a person with
filesystem access can still open the artifacts. Do not inspect outcomes until
model/analysis choices are frozen, and record any accidental unblinding.

Pilot pairs 3-4 subsequently completed; all four pilot pairs and all eight
held-out groups are now collected. Held-out groups are not scored
results, reviewed labels, or approved model datasets. The requested pair-7-to-12
batch completed sequentially without failed pairs, replacement attempts, or
retries. No outcome-count distributions or paired deltas were inspected during collection.
The declared labels and independent-review status remain unchanged. User
permission enables bounded collection but does not prove reviewer independence.
See the [pilot completion and analysis lock](pilot_completion_20261003.md)
for collection progress and frozen descriptive-analysis choices. Subsequent
scoped descriptive unblinding is recorded in the
[held-out results report](benign_held_out_descriptive_20261003.md). These outcomes
are now inspected and cannot be treated as unseen data for later revised analyses.

The original gNB PID `63862` and UE PID `64022` remained present after pair 12
at `2026-10-03T13:06:41+08:00`. The free5GC revision remained
`4aa237be57404dea5b49ca8f332c6e25ede052de`. No user-plane continuity test was
performed. No alert, inference, model deployment, or enforcement action ran.

## Reproduction Boundary

The CLI now permits pairs 1-12, but pairs 5-12 require `--authorization`:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_benign_control_pair.py \
  --execute-benign --pair-id 7 \
  --pair-dir "$PWD/data/input_testing/<new-held-out-pair-directory>" \
  --registered-nf-instance-id <authorized-current-amf-uuid> \
  --authorization evaluation/scoped_live_authorization_20261003.json
```

The example illustrates the CLI syntax only: pair 7 has now executed, so its
existing directory must not be reused and no replacement collection is implied.
New AMF identities require a newly scoped
authorization; there is no automatic target substitution or authorization
escalation. Existing pair directories are refused, failed attempts remain
visible, and both conditions/all adjacent windows stay in the same partition.
No permission here authorizes rate limiting, UE disconnection, NF restart,
subscriber changes, or deployment of an unvalidated model.