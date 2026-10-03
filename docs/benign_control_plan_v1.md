# Benign-Control Pilot Plan

## Frozen Scope

The prospective specification is
[baseline_control_plan_v1.json](../configs/baseline_control_plan_v1.json).
Preserve its SHA-256 in every future block manifest before collection; changes
require a new version and a recorded amendment, not retrospective edits.
This is a frozen collection/analysis design, **not an executed campaign or an
approved detector**. Model fitting and mitigation remain disabled.

The first controlled question is whether the same passive collector observes
a known benign signaling operation differently from a matched no-request block.
It is not yet whether telemetry detects malformed NAS or a vulnerability.

## Matched Design

Collect twelve matched pairs, each containing a passive block and a block with
one existing fixed authenticated read-only NRF discovery GET. Each block uses
the same thirty-second warmup, three nominal ten-second windows, one-second
cadence, two-second timeout, source contract, parser revision, and resource
limits. Keep the active UE and gNB unchanged. The operation occurs within the
middle window; its exact request hash and observed start/end must be recorded
and verified against the actual monotonic boundaries.

The configuration fixes balanced counter-ordering in advance. Four pairs are
pilot-only; eight are reserved for the prospective held-out summary. Keep both
conditions and all consecutive windows from a pair together. Actual durations
and errors remain visible. Failed blocks are evidence, not candidates to discard
until the experiment looks successful. Any replacement needs a documented plan
amendment and new identities. Twelve pairs are a feasibility pilot, not a power
calculation or sufficient proof of efficacy.

Primary analysis is the within-pair difference in middle-window SBI event count.
Report paired values and their distribution, not an inflated sample size based
on correlated windows. Report readiness failures, actual durations, Linux
measurements, SBI errors, and PFCP counts separately. Direct observation of the
benign GET is expected instrumentation behavior, not a security anomaly.
Background PFCP changes do not establish a causal effect of the GET.

## Execution Boundary

At plan freeze, the passive capture runner existed but the synchronized
benign-action runner was still outstanding. The standalone NRF runner's successful
request does not establish a matched middle-window condition. Do not run it beside an
uncoordinated collector and claim synchronized evidence. Existing pilot captures
are excluded from future held-out evaluation because their outcomes were already
inspected before this plan was frozen.

Implementation update: the synchronized runner now exists as
`scripts/run_benign_control_pair.py`; its first authorized live pilot pair is
documented in the [pair-1 report](benign_control_pair01_20261003.md). The frozen
JSON plan and its historical prerequisite wording remain unchanged. Execution
progress is recorded separately in pair journals, not by editing the plan.
The runner preserves its default passive behavior and requires explicit benign
authorization. All four pilot pairs have now executed; see the
[pair-2 provenance and review report](benign_control_pair02_20261003.md).
Label review and model approval remain outstanding. Execution receipts, not
changes to the frozen plan, record the implementation revisions and results.
The [pilot completion report](pilot_completion_20261003.md) records pairs 3-4
and a separate descriptive-analysis lock before held-out unblinding.

No inference should be enabled merely because all sixteen fields are populated.
An eventual model needs its own data and feature-semantics manifest, reviewed
labels, grouped partitions, and frozen training/threshold decisions before
held-out scoring. Passive-only data can support baseline characterization but
cannot establish sensitivity to reviewed failures. The historical 21-feature
model remains blocked for this reduced contract.

## Evidence Revalidation

The new checker reprocesses `capture.json`, compares stored reports, window
metadata, vectors and snapshot streams, and hashes artifacts. It reports feature
variation without generating scores or promoting declared labels to truth:

```bash
PYTHONPATH=src .venv/bin/python scripts/summarize_baseline_evidence.py \
  --campaign-dir data/input_testing/passive-three-source-20261003-v3 \
  --output evaluation/passive_baseline_evidence_20261003.json
```

Output creation is exclusive; an existing report is never overwritten. Repeat
`--campaign-dir` for additional distinct captures. Capture hashes identify
groups for future partitioning, but a matched pair should be assigned a common
group ID across both conditions. Hash identity checks do not attest authenticity.

The checker is not a readiness certificate for model evaluation: label review,
matched benign controls, and confirmed-case conditions remain separate gates.