# RNAS0001 Historical Telemetry Recovery

## What Was Recovered

On 2026-10-03 the referenced historical free5GC log was read without replaying
any NAS input or changing testbed state:
`~/free5gc/log/20261002_200341/free5gc.log`.
The source file was 386,186 bytes, unchanged during the bounded read, with SHA-256
`33134d9795cbdc46df9558596ca14214554a39ca82713fd1d505cfd1ecf9c800`.

The extraction used the original case window with nanosecond precision:
`2026-10-02T20:58:34.634928027+08:00` through
`2026-10-02T20:58:41.040804795+08:00`, inclusive. Context before/after is
preserved separately for fifteen seconds on each side; it is not counted as
within-run telemetry. No timestamped lines in this source failed the timestamp
parser. Untimestamped lines are not included.

| Phase | Parsed SBI Access Records | PFCP Log Records | Other Core Log Records |
| --- | ---: | ---: | ---: |
| Before, up to 15 seconds | 0 | 2 | 0 |
| Original case window | 12 | 0 | 45 |
| After, up to 15 seconds | 0 | 4 | 3 |

The recovered within-window SBI statuses were nine NRF HTTP 200 responses and
one HTTP 404 each from UDR, UDM, and AUSF. These are shared-core log observations,
not proof that all twelve records were caused by the test UE. No request paths,
subscriber identifiers, client addresses, tokens, credentials, or raw messages
are exported. Source line numbers permit authorized local verification without
publishing raw logs.

## Rejection and Cleanup Observations

Sanitized pattern markers identify:

- NG Setup-related activity at source line 1298.
- Authentication-subscription-related activity at line 1332.
- Registration-reject-related activity at lines 1338 and 1343.
- SCTP shutdown-related activity at line 1346.
- RAN removal-related activity at lines 1347 and 1349-1351.

These observations support the historical receipt's authentication-path failure
and cleanup observations. Markers are coarse log-pattern annotations, not proof
of precise protocol semantics, UE identity attribution, or a successful release
handshake. No Release Command/Complete marker was found in the extraction;
absence of such a marker is not proof the messages never occurred.

The malformed-input causal claim remains unestablished. A real NAS test took
place, but the authentication data failure prevents classifying this rejection
as a confirmed fuzz-triggered anomaly.

## Linux and Packet Archive Check

The following candidate archive directories were absent on the testbed:

- `/var/log/sysstat`
- `/var/log/sa`
- `~/free5gc/research/data`
- `~/free5gc/research/results`
- `~/free5gc/research/output`
- `~/nwdaf-research/data`

An earlier metadata search within the inspected research and referenced run-log
paths found no matching JSONL or pcap archives. This is a bounded search, not a
claim that no monitoring data exists anywhere on any machine. No historical
Linux samples or packet capture have been located. Provide another archive
path if monitoring was stored elsewhere.

## Partial Sixteen-Field Record

[rnas0001_partial_features_20261003.json](../evaluation/rnas0001_partial_features_20261003.json)
contains all sixteen field names, but only six recoverable values: recorded UTC
duration 6.405876768 seconds, twelve SBI records including three HTTP errors,
and zero matching PFCP records/requests/responses. The remaining eight Linux
fields and two availability flags are `null`, not zero-imputed.

The record explicitly remains `INCOMPLETE` and `training_ready: false`.
It is a source-bound historical statistic record, not a valid online feature
vector. Inclusive historical log filtering and unknown collector health differ
from the validated online counter-window contract. Do not train the existing
sixteen-feature model by filling these missing values or copying another run.
Reliable completion requires actual historical monitoring/health evidence or
new independently collected, fully synchronized case observations.

## Interpretation Boundary

The recovered report is
[rnas0001_retrospective_logs_20261003.json](../evaluation/rnas0001_retrospective_logs_20261003.json).
It is **partial retrospective telemetry**, not a newly collected complete run.
In particular:

- SBI/core metadata can be recovered from the original time window.
- Zero matching PFCP records is an observed log-extraction count, not a verified
  healthy-collector zero or proof of no PFCP traffic.
- Linux measurements, collector health at execution, monotonic clock identity,
  and packet/kernel completeness remain unavailable.
- Current collector health cannot retroactively establish historical health.
- No sixteen-feature vector, anomaly label, or detector metric is fabricated.

The original receipt, missing `runs/RNAS0001` bundle, and historical evidence
summary remain unchanged. The earlier statement that no NWDAF-format run bundle
was collected is still correct; this recovery adds authentic log observations
without rewriting the acquisition history.

To repeat the same bounded extraction into a new output:

```bash
.venv/bin/python scripts/recover_rnas0001_logs.py \
  --output evaluation/<new-recovery-report>.json
```

The script has no seed, target, replay, or privilege options; its only network
operation is read-only SSH acquisition from the existing configured testbed.
Existing outputs are refused. Original source hashes and retrospective status
must accompany any later use of these observations.