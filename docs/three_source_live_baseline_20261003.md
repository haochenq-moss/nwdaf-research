# Three-Source Live Baseline: 2026-10-03

## Scope Decision

The first Fuzz-to-NWDAF collection milestone uses the explicit
`linux-sbi-pfcp-v1` contract. This is a separate 16-feature profile, not an
implicit weakening of the existing `full-six-source-v1` default. Process,
free5GC general-log, and eBPF feature fields are absent rather than fabricated
as zeros. Both profiles retain their own required health sources and counters.

The historical model is not approved for the reduced profile.
`score_live_window` returns `MODEL_NOT_APPROVED` for a ready reduced-profile
window without training or prediction. A separately evaluated model and
feature-semantics contract are required before baseline inference.

## Actual Live Evidence

The passive capture adapter ran a synchronous observation loop on the Ubuntu
testbed through the existing SSH tunnel. It read `/proc/loadavg`, `/proc/meminfo`,
and newly appended existing core log lines. It did not send NAS or NRF stimuli,
change routes/subscribers, request privileges, restart functions, or perform
mitigation. SSH transport itself is used; `network_transmission_executed: false`
in these receipts means no generated testbed protocol stimulus, not zero SSH
network packets.

The successful campaign is
[passive-three-source-20261003-v3](../data/input_testing/passive-three-source-20261003-v3/report.json).
Shared monotonic warmup coverage was **30.003098211 seconds**, with no admission
errors. Three consecutive measured windows passed the reduced readiness contract:

| Window | Measured Duration (s) | Features | Linux Samples | SBI Events | PFCP Events | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| WBASE001 | 10.003946 | 16 | 10 | 0 | 1 | READY |
| WBASE002 | 9.993823 | 16 | 10 | 0 | 1 | READY |
| WBASE003 | 10.001180 | 16 | 10 | 0 | 3 | READY |

Each lifecycle records `ACCUMULATING -> READY`. There is deliberately no
`INFERENCE_COMPLETE`, anomaly probability, or claim of detection efficacy.
The short, slightly variable durations are actual monotonic poll-boundary
intervals, not mislabeled exact ten-second periods.

Post-capture checks found the original gNB PID `63862` and UE PID `64022` still
present. This is process-preservation evidence, not an end-to-end user-plane
availability test. No existing campaign artifacts were overwritten.

## Health and Clock Meaning

The new synchronous adapter emits health after successful bounded Linux and
log-cursor reads. It does not infer health from an empty output file. Known-log
read failures, truncation/replacement, parser exceptions, excessive inventory,
and exhausted read/evidence budgets are recorded as failures. Healthy zero
event deltas remain valid. Its log scope is the newest timestamped run directory
containing `free5gc.log`; historical content starts at EOF and is excluded.

The adapter maintains a host/boot `CLOCK_MONOTONIC` identity. One UTC anchor is
projected using monotonic offsets for window processing; later wall-clock steps
do not change durations. Records explicitly label this
`CLOCK_MONOTONIC_PROJECTED_UTC`, not physical UTC. Counter cuts and health
watermarks denote completed observation-time reads, not kernel or packet-time
watermarks. Parser outputs are sanitized; raw log lines and subscriber data
are not exported.

SBI/PFCP remain **log-derived metadata**, not packet capture. Successful reads
do not prove every semantic event was logged or recognized by the existing
parsers. SBI zeroes mean no matching new events in the selected logs during
these observation windows, not absence of all SBI traffic. Background PFCP
events cannot be attributed to a fuzz stimulus, since none was generated.

## Preserved Failed Attempts

- [First capture](../data/input_testing/passive-three-source-20261003/report.json):
  all three windows unavailable because the broad archive inventory exceeded
  its cap; the host contained 254 historical log files. The cap was not raised.
- [Second capture](../data/input_testing/passive-three-source-20261003-v2/report.json):
  current-run scope passed, but existing collector parser signatures and required
  instance fields were not adapted correctly. Parser errors failed closed.
- Third capture: after a regression-tested scope and interface repair, warmup
  and windows passed. Failed records remain unchanged for audit.

## Reproduce and Next Gate

From the NWDAF repository, choose a new campaign path:

```bash
PYTHONPATH=src .venv/bin/python scripts/capture_passive_windows.py \
  --campaign-dir "$PWD/data/input_testing/<new-passive-campaign>" \
  --window-count 3 --duration-sec 10
```

The operation includes a fixed thirty-second warmup and is runtime-bounded.
It uses no sudo and cannot enable inference or mitigation. An existing campaign
path is refused before acquisition.

The next milestone is matched benign controls, independent outcome review, and
a frozen model/evaluation plan for this contract. Three passive windows validate
plumbing, not normal-distribution calibration, fuzz-triggered observability,
held-out detection quality, or response safety. Related mutation families and
identical input bytes must still be grouped in later evaluation splits.