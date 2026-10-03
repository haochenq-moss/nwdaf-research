# Live Adaptation Preflight: 2026-10-03

This campaign preserves actual read-only observations from the private Ubuntu
free5GC testbed. The active UE and gNB were left running; no subscriber data,
routes, NF processes, or enforcement settings were changed.

The user's goal is live Fuzz-to-NWDAF adaptation, not only offline staging.
This capture establishes the benign live collection path, not NAS fuzz replay
or live mitigation.

## Observed Evidence

- Reverse SSH connection to the configured private testbed succeeded.
- All nine checked free5GC functions were running at revision
  `4aa237be57404dea5b49ca8f332c6e25ede052de`.
- A gNB and UE process were present. Current AMF logs contained a Registration
  Complete event for the existing synthetic control UE.
- Read-only MongoDB counts showed one authentication subscription record for
  each of the control and separate replay subscribers. Credentials were not read.
  Record presence does not establish successful replay-subscriber authentication.
- Run `RLIVE-NRF-20261003-01` performed one existing fixed, authenticated NRF
  discovery request: HTTP 200, duration 743.138 ms, four Linux samples, two SBI
  events, and two PFCP events. The OAuth token was not persisted.
- The PFCP observations are background events during capture, not effects
  causally attributed to the NRF GET request.

## Live Analytics and Limits

The existing read-only analyzer subsequently scored a real snapshot. Its output
is preserved in
[live_adaptation_preflight_20261003.json](../../../evaluation/live_adaptation_preflight_20261003.json).
The model returned `ANOMALY` with probability 0.955. This is not a validated
security conclusion: a sparse snapshot was supplied to a run-level model,
several measurements were unavailable, and no matched controls or causal
fuzz stimulus were present. Rolling log-tail counts are not per-run event rates.

The observer lacked UE namespace visibility. A zero host-visible tunnel count
must not be interpreted as absence of the active UE or proof of service failure.
Autonomous response eligibility was false. No mitigation was executed.

## Guarded Live Scoring

The live CLI now uses `score_live_features` rather than zero-filling missing
inputs through unrestricted feature scoring. Missing, non-finite, invalid, or
explicitly unavailable measurements cause `INSUFFICIENT_EVIDENCE`, with no
prediction call, anomaly probability, or actionable verdict. Complete vectors
can receive exploratory scores but do not authorize a response.

The follow-up real live check is preserved in
[live_adaptation_guarded_20261003.json](../../../evaluation/live_adaptation_guarded_20261003.json).
It identified 14 missing trained-model inputs and abstained. These include run
duration and Linux/SBI/PFCP counts. The earlier 0.955 result remains preserved;
it is not superseded by a claimed normal verdict or validated detection result.
This compatibility guard does not verify collection semantics or distribution
match. Window-complete, collector-availability-aware telemetry remains necessary.

No malformed NAS input was sent. Newly drafted NAS execution tooling was removed
before deployment or live execution; the user's pre-existing remote probe source
and binaries were left untouched. Live protocol replay remains a separately
reviewed experiment rather than a completed capability of this campaign.

This campaign has one input-test run and no held-out or matched normal runs.
It is not ready for detection-quality evaluation or claims of live adaptation
efficacy. Next defensive work is telemetry-complete benign control collection,
feature compatibility checks, and an analyst-reviewed observation workflow.