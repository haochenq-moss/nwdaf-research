# Provenance-Verified Benign Pilot Pair 2

## Measured Result

Pilot pair 2 ran in frozen reversed order: **benign NRF first, passive second**.
Both blocks passed the thirty-second warmup and all three collection windows.
Each window contains sixteen baseline features and ten Linux samples. The
fixed token POST and discovery GET both returned HTTP 200; full operation
duration was **114.495324 ms**, with **5.710551 ms** for discovery. The receipt
places the entire operation inside the actual middle-window boundaries.

| Condition | Window | Duration (s) | SBI Events | SBI Errors | PFCP Events |
| --- | --- | ---: | ---: | ---: | ---: |
| Benign NRF | WBASE001 | 10.011998 | 0 | 0 | 3 |
| Benign NRF | WBASE002 | 9.989989 | 2 | 0 | 1 |
| Benign NRF | WBASE003 | 9.996913 | 0 | 0 | 1 |
| Passive | WBASE001 | 9.998241 | 0 | 0 | 1 |
| Passive | WBASE002 | 10.021900 | 0 | 0 | 1 |
| Passive | WBASE003 | 9.977540 | 0 | 0 | 3 |

The middle-window SBI difference is **+2**, consistent with the two benign
HTTP operations. This repeats pair 1's observation with reversed ordering,
not an anomaly-detection result or a statistically established effect.
Background PFCP changes remain unattributed.

Artifacts are preserved under
[benign-control-pilot-pair02-20261003](../data/input_testing/benign-control-pilot-pair02-20261003/pair_summary.json).
The original gNB PID `63862` and UE PID `64022` remained present after capture.
No NAS input, subscriber/route mutation, privileged setup, inference, or
mitigation was performed. Process presence does not verify user-plane service.

## Parser Provenance Improvement

The adapter now hashes each actual remote parser source file before import,
checks imported module path resolution, and rechecks contents on every poll.
Hashes are stored in raw captures and manifests. A read/hash failure, changed
file, missing hash, or cross-block mismatch fails closed or withholds the pair
delta. The frozen collection plan was not changed; new local collector/control
and transmitted source hashes distinguish this implementation revision.

Both blocks recorded identical parser file hashes:

- SBI: `7fd216c3b1b9f58b10ee2bcc916f0eed4c438664e75bd5cea9fb4715cb5cbfe5`
- PFCP: `d739ca926fd3d51ab2a219750499b01c7dc9e5bef465ddce5fcbc5bfb71ca861`

These establish file-content consistency during observation, not cryptographic
attestation of all loaded Python bytecode or dependencies. They do not establish
which files were used for historical pair 1. That capture remains unchanged
and retains its original provenance limitation. Legacy captures remain readable;
new matched-pair execution requires hashes.

## Independent Review Still Pending

An analyst other than the execution agent must review each pair before promoting
declared conditions to reviewed outcome labels. The following checks are a
review request, not an approval or a claim of reviewer independence:

1. Verify the frozen plan hash, pair ID/order, pilot partition, attempt ID, and
   local/transmitted collector hashes against the saved artifacts.
2. Recompute window readiness from raw captures and verify exact saved vectors,
   snapshot streams, source health, counter baselines, and boundary durations.
3. Verify the fixed request identity, both HTTP statuses, bounded operation,
   and complete auth/GET interval within window two. Check failed or interrupted
   attempts remain visible; none may be selectively erased.
4. Review fixture evidence and competing background activity. Do not infer
   service continuity solely from unchanged process IDs or call the benign
   request an attack because its SBI count increased.
5. Record reviewer identity, UTC review time, decision (`approved`, `rejected`,
   or `inconclusive`), rationale, and exact artifact SHA-256 references in a
   separate review sidecar. Keep `label_review: not_performed` until that review
   actually occurs; do not overwrite acquisition labels or receipts.

Pairs 1 and 2 are pilot-only. No held-out pairs or model fitting have run. Keep
both conditions and all correlated windows from a pair within one partition;
the two pairs must also retain their differing implementation-provenance strata.
This milestone closes the parser-file hash gap for future captures, but does
not establish security detection, score calibration, or response efficacy.