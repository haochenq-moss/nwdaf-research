# Synchronized Benign-Control Pilot Pair 1

## Execution and Evidence

On 2026-10-03 the authorized runner executed **one pilot matched pair** under
the unchanged frozen plan, SHA-256
`1589f643ddd1bfcf5fd068c21f3d682ef5d6504242afc5d0883f1a3788b17b77`.
The fixed order was passive then benign NRF. Each block used a thirty-second
health warmup, three nominal ten-second windows, one-second polling cadence,
two-second health timeout, and the `linux-sbi-pfcp-v1` contract. All six windows
passed collection readiness. No additional pilot or held-out pairs were executed.

Artifacts are in
[benign-control-pilot-pair01-20261003](../data/input_testing/benign-control-pilot-pair01-20261003/pair_summary.json).
The directory includes an intent/progress journal, an exact frozen-plan copy,
collector/control/transmitted-code hashes, both raw sanitized captures, per-window
streams and vectors, and the synchronized operation receipt. Existing evidence
was not overwritten; failed or interrupted future pairs retain their journals.

## Measured Windows

All windows contained sixteen features and ten measured Linux samples:

| Condition | Window | Duration (s) | SBI Events | SBI Errors | PFCP Events |
| --- | --- | ---: | ---: | ---: | ---: |
| Passive | WBASE001 | 10.009546 | 0 | 0 | 1 |
| Passive | WBASE002 | 10.024520 | 0 | 0 | 3 |
| Passive | WBASE003 | 9.964392 | 0 | 0 | 1 |
| Benign NRF | WBASE001 | 9.997173 | 0 | 0 | 3 |
| Benign NRF | WBASE002 | 10.010069 | 2 | 0 | 1 |
| Benign NRF | WBASE003 | 9.989647 | 0 | 0 | 1 |

The primary pilot observation is the middle-window SBI count difference,
benign minus passive: **+2**. The benign operation includes an OAuth token POST
and one discovery GET; the two observed events are consistent with those
requests, not a confirmed security anomaly. No causal effect on background PFCP
is established.

## Receipt and Synchronization

The token POST and fixed GET both returned HTTP 200. Full operation duration was
**1086.574886 ms**; discovery duration was **297.587051 ms**. Recorded monotonic
start/end markers place both authentication and discovery inside the actual
middle-window boundaries, after the health-admitted trigger at sample 41.

The request-target identity is the existing fixed discovery path, hashed from
the exact path plus newline:
`d25edf729beac2de92eaa6256840654661a01867f8701f0d2ad1c4e81a026eb0`.
This identifies the target, not the complete HTTP wire request. Authorization
headers/token values and response contents are excluded from evidence.

The worker is separate from synchronous polling, has a 4.5-second operation
deadline, refuses redirects/proxies, uses bounded reads, and does not retry
failed requests. A failed health warmup suppresses the request. A failed,
mistimed, incomplete, or non-2xx operation cannot produce a valid paired delta.

## Preservation and Limits

Post-pair checks found the original gNB PID `63862`, UE PID `64022`, and pinned
free5GC revision `4aa237be57404dea5b49ca8f332c6e25ede052de` unchanged. No NAS
input, subscriber mutation, route change, NF restart, privileged command,
inference, or mitigation was performed. Process presence is not a user-plane
service-continuity test.

Label basis remains `declared_by_protocol_not_validated`. The pair is pilot
evidence, not an independent held-out result. It shows synchronized benign
signaling observability through the log-based polling contract; it does not
measure fuzz-triggered detection, vulnerability classification, anomaly-score
stability, or response efficacy. One pair does not estimate a distribution.

Local collector/control and transmitted source hashes are preserved. Remote
parser matching currently uses pinned revision and path metadata, not independent
hashes of each parser file; local uncommitted remote parser changes are therefore
a remaining provenance limitation. Log observation-time watermarks are not raw
packet/kernel event-time watermarks.

## Reproduction Boundary

The runner requires explicit `--execute-benign` and a current registered AMF UUID:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_benign_control_pair.py \
  --execute-benign --pair-id 2 \
  --pair-dir "$PWD/data/input_testing/<new-pilot-pair-directory>" \
  --registered-nf-instance-id <current-registered-amf-uuid>
```

This example would run the next pilot pair, with its order selected from the
frozen plan; it has not been executed. Existing pair directories are refused.
The CLI permits pilot IDs 1-4 only, not automatic held-out execution. Before
continuing, independently review this pair's receipt/fixture evidence and
resolve the remote parser-hash limitation. Inference and mitigation remain off.