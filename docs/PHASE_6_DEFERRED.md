# Phase 6: Deferred Agent and NEMOIR Work

## Status
This phase is intentionally deferred and not implemented in the current repository state.

## Conditions for activation
The downstream agent/NEMOIR stage may be considered only after all of the following are complete and verified:

1. The offline analytics baseline is validated on the preserved whole-run split.
2. The dataset evidence and model assumptions are documented and reproducible.
3. The telemetry source is limited to the verified Linux metadata and events actually present in the archive.
4. No fabricated free5GC, PFCP, SBI, or live runtime telemetry is introduced.

## Guardrails
- Do not implement agent logic before the dataset-first analytics baseline is stable.
- Do not claim NEMOIR or free5GC integration before the offline pipeline is validated.
- Do not mix model predictions, agent hypotheses, and observed telemetry in the same evidence stream.
- Keep all user-facing claims grounded in measured results from the transferred dataset.

## Future work once activated
When the analytics baseline is mature, the downstream phase may include:
- agent orchestration over validated analytics outputs
- NEMOIR-driven narrative or reasoning layers downstream of evidence
- structured reporting on model findings, not speculative runtime claims

## Current project position
The current repository is intentionally capped at the offline, evidence-based analytics layer. Agent and NEMOIR remain future work only.
