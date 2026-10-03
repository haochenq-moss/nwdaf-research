# Window Verification: 2026-10-03

## Synthetic Fault Verification

The following unit tests use synthetic measurements and mocked model inference.
They are software verification, not live experiment results.

| Case | Verified result |
| --- | --- |
| Freeze only the eBPF heartbeat while all other sources refresh | At the timeout boundary the window can accumulate; once age exceeds the threshold it becomes `COLLECTOR_UNAVAILABLE`, with no feature extraction. |
| Process restart/decreasing cumulative process counter mid-window | Sealed window returns `INSUFFICIENT_EVIDENCE`, records the regression, and exposes no feature vector. |
| Three consecutive healthy zero-subscriber-event windows | Each provides all 21 feature names and reaches inference; Linux sampling continues while network/process/eBPF event deltas remain zero. |
| Lifecycle logging | Ingestion records timestamped `ACCUMULATING` then `READY`; actual successful prediction appends `INFERENCE_COMPLETE`. |

Lifecycle state is separate from `predicted_label`. `INFERENCE_COMPLETE` means
the model ran, not that the prediction is correct, normal, or actionable. Failed
feature compatibility remains `INSUFFICIENT_EVIDENCE`. No output grants response
authorization. Repeated readiness checks in the same state do not add duplicate
lifecycle entries.

The clean-zero test's mocked score cannot demonstrate stability of the deployed
model. It specifically proves that genuine zero event deltas do not prevent
inference when collectors and time coverage are healthy.

## Live Testbed Preflight

Read-only checks at `2026-10-03T11:05:49+08:00` found the active gNB process
`63862` and UE process `64022`. They were not stopped or reconfigured.

The testbed has `/usr/bin/bpftrace`, but the SSH session runs as UID 1000 with
effective capability mask `0000000000000000`. The kernel reports
`unprivileged_bpf_disabled=2`; no `bpftrace` process was running. Inspection of
the existing eBPF collector confirms it reports unavailable when its
root/capability prerequisites fail, rather than generating valid zero events.
Existing inspected collectors do not emit the window heartbeat/watermark
contract. No privileged setup or probe attachment was attempted.

Consequently, a three-window live `READY`/inference cycle was **not performed**.
There are no measured baseline window scores or evidence of non-spurious
baseline classification from this check. The current full contract requires
all six sources; eBPF cannot be silently disabled to make readiness pass.

## Live Acceptance Gate

1. An operator provisions a reviewed collector service with only the necessary
   privileges for actual eBPF attachment. It reports verified attachment,
   ongoing health, and exporter synchronization. Do not broaden interactive
   sudo access or weaken kernel policy simply to satisfy the gate.
2. Exporters for Linux, process, SBI, PFCP, free5GC, and eBPF emit genuine
   heartbeat-bearing snapshots and flushed-through watermarks using the
   [window contract](telemetry_windows.md). A running thread/file alone is
   insufficient health evidence; swallowed read errors must surface as failures.
3. Capture at least three consecutive sealed baseline windows with the active
   UE unchanged. Preserve records, boundary timestamps, lifecycle entries,
   collector states, feature vectors, and model identity.
4. Verify all 21 features and monotonic counters, then assess observed scores.
   Do not equate stable scores with correctness or tune thresholds using the
   same baseline windows. Source-availability semantics must match the evaluated
   model contract; historical nonempty-stream flags differ from health flags.
5. Report false positives and score variation honestly. Three windows are a
   smoke check, not a statistical detection-quality evaluation. If collection
   fails, record `COLLECTOR_UNAVAILABLE` rather than supplying synthetic zeros.