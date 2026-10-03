# Pilot Completion and Analysis Lock

## Collection Complete

Pilot pairs 3 and 4 completed under the unchanged frozen collection schedule:

| Pair | Order | Block Readiness | Middle-Window SBI Difference |
| --- | --- | --- | ---: |
| 3 | Benign NRF, passive | Both READY | +2 |
| 4 | Passive, benign NRF | Both READY | +2 |

Each pair preserved matching parser hashes, healthy warmup, six ready windows,
and an operation receipt validated inside window two. Acquisition labels remain
declared, not independently reviewed. No inference or mitigation ran. Original
gNB PID `63862` and UE PID `64022` remained present after collection; this is not
a user-plane availability test.

All twelve planned pairs are now collected: four pilot pairs and eight held-out
pairs. Pilot SBI differences were +2 in all four pairs. Held-out counts, feature
distributions, and deltas have not been inspected. Collection completion does
not establish detection efficacy or a model suitable for deployment.

Pending human review packets were generated for
[pair 3](../evaluation/analyst_review_pair03_20261003/review_packet.json) and
[pair 4](../evaluation/analyst_review_pair04_20261003/review_packet.json).
Both contain 27 bound artifacts and unsigned decision drafts. No reviewer
identity, independent approval, or completed checks were invented.

## Analysis Choices Locked Before Unblinding

[benign_control_analysis_lock_v1.json](../configs/benign_control_analysis_lock_v1.json)
fixes the next descriptive analysis. It was written after pilot inspection and
held-out acquisition, but before held-out outcome inspection. This is not a
claim that every analysis choice was preregistered before data collection.
The original collection plan remains unchanged.

Primary endpoint: the middle-window SBI count difference within each matched
pair. Report every held-out pair, median/range, and positive/zero/negative counts.
Secondary descriptions cover collection errors, durations, SBI errors, PFCP
and Linux measurements. No hypothesis test, classifier fitting, threshold
selection, inference, or mitigation is part of this lock. Both conditions are
benign; learning to recognize a known HTTP request would not establish a
security detector.

Invalid pairs retain their evidence and null endpoints rather than becoming
zeroes or being silently replaced. Recompute windows and synchronization from
raw capture before accepting a stored delta. Keep implementation hashes visible
and adjacent windows grouped. Report log-derived metadata as such; do not infer
raw packet coverage or causal NRF effects on background PFCP.

## Next Gate

The lock does not itself authorize unblinding. Human review remains pending,
and the current execution permission requires outcomes to stay uninspected until
analysis choices are frozen. A separately recorded decision to unblind for this
descriptive purpose should bind the lock hash and explicitly preserve the
no-model/no-mitigation scope. Later anomaly evaluation needs independent labels
and suitable reviewed-case data, not relabeling these benign operations as attacks.