# Live Telemetry Operator Checklist

## Current Host and Deployment Boundary

Read-only checks on 2026-10-03 observed Linux `5.15.0-139-generic`, systemd
`245.4-4ubuntu3.24`, and bpftrace `0.9.4`. The gNB and UE remain active. The
unprivileged session has no effective capabilities and the kernel reports
`unprivileged_bpf_disabled=2`. No service, user, permissions, or kernel policy
was changed. No thirty-second healthy-source admission or three-window live
inference acceptance run has been completed.

## Capability and Service Review

- Use a dedicated non-login service account and root-owned, non-service-writable
  executable/configuration. Never grant capabilities to a general-purpose shell
  or interpreter. Ambient capabilities also reach subprocesses; keep the
  executable, plugin, and dependency paths operator-controlled.
- For the current `sys_enter_execve` tracepoint, start the review with `CAP_BPF`
  and `CAP_PERFMON`. `CAP_NET_ADMIN` is not a blanket requirement for all socket
  or skb tracepoints; add it only when a specific network attachment/operation
  requires it. Do not grant traffic-enforcement privileges to passive analytics
  by default.
- The capability split arrived with Linux 5.8, but the exact probe, tool version,
  kernel configuration, LSM, tracefs permissions, and systemd/libcap recognition
  still matter. On older kernels `CAP_SYS_ADMIN` may be necessary for some BPF
  operations, but it is broad privilege, not an equivalent least-privilege
  fallback. Stop for a separate review rather than automatically adding it.
- Verify that systemd 245 and its installed capability library recognize the
  requested names; kernel 5.15 alone does not establish userspace support. Older
  bpftrace behavior may also require review or upgrade. Do not assume the
  service template works merely because its syntax looks correct.
- Review the
  [service template](../configs/systemd/free5gc-ebpf-collector.service.example).
  `/opt/telemetry/bin/ebpf_collector` is an external, unimplemented executable
  placeholder, not a binary supplied by this repository. The unit does not
  create exporter health support. Do not install it unchanged.
- The operator must verify real attachment, expected tracepoint events, drop
  accounting, effective service capabilities, output permissions, and the
  hardening settings with the chosen collector. Empty files/process presence
  are not proof of health. A restart invalidates admission and in-flight windows.
- Keep service output in its managed state/runtime directories. Other sources
  must have separately reviewed access to core logs and process metadata; do
  not relax `ProtectHome` globally to read everything under a user home.

Privileged installation and service activation are operator actions on Ubuntu,
not actions to perform from this analytics session. Validate the final rendered
unit with the target host's `systemd-analyze verify` before activation. Record
the installed unit/configuration hashes. For rollback, stop only the new
collector service, verify its owned probes are detached, and remove only its
owned unit/configuration. Never restart the core or active UE as a shortcut.

## Heartbeat Admission Contract

The implemented `HeartbeatReadinessGate` validates all six primary sources:
`linux`, `process`, `sbi`, `pfcp`, `free5gc`, and `ebpf`. Each source publishes
records in a common, explicitly identified host/boot monotonic clock domain:

```json
{
  "source_id": "ebpf_kernel_probe_01",
  "collector_instance_id": "new-id-for-each-process-start",
  "clock": "CLOCK_MONOTONIC",
  "clock_domain": "testbed-host/boot-id/CLOCK_MONOTONIC",
  "status": "HEALTHY",
  "timestamp_ns": 31000000000,
  "sequence_no": 31,
  "window_watermark_ns": 31000000000,
  "metrics_summary": {"events_observed": 142, "drops": 0}
}
```

The numbers above are illustrative boot-relative nanoseconds, not epoch UTC.
Provide `received_at_ns` from the **same host/boot clock** when admitting a
record. A receiving analytics server's monotonic clock cannot be substituted.
UTC timestamps may accompany records for audit, but cannot replace duration
and freshness measurements. Host identity, boot ID, and collector instance ID
prevent accidental mixing across reboots, hosts, and process restarts.

Default interval is one second, timeout two seconds, and required shared
coverage thirty seconds. Timeout must not exceed twice the configured interval.
Missing sources immediately produce `COLLECTOR_UNAVAILABLE`; heartbeat expiry
occurs once its age exceeds the timeout, not immediately between valid heartbeats.
All sources need overlapping coverage; a late source delays admission. Sequence
numbers and timestamps increase strictly, cumulative event counts and watermarks
never decrease, and zero event counts are legitimate. Drops, malformed records,
identity changes, out-of-order messages, and coverage gaps fail closed. After a
fault, create a fresh admission gate and collect another full warmup; do not
delete fault history to make the old gate pass.

During admission a watermark may lag by at most the timeout; at a window seal
every source must have flushed through the exact seal boundary. `HEALTHY` must
come from actual collector attachment/read-loop readiness, error/drop checks,
and synchronized consumption, not exporter uptime alone.

## Clock Bridge and Exporter Work Remaining

The heartbeat gate is implemented and tested independently. Existing remote
collectors do not yet emit this protocol. The current `TelemetryWindow` uses
timezone-aware UTC boundaries; it is **not yet a CLOCK_MONOTONIC accumulator**.
Never convert a boot-relative timestamp using `datetime.fromtimestamp` or feed
it into the existing UTC JSONL interface as if it were epoch time.

A reviewed host-side adapter must first validate admission, retain the clock
domain/boot mapping, and use monotonic offsets for all window boundaries,
counter cuts, and seals. UTC is an audit mapping only. Wall-clock jumps must not
alter a window's duration or duplicate/discard events. Test that bridge with
NTP-step simulations before treating this contract as end-to-end implemented.
This document and the example unit do not deploy that adapter.

## Post-Provisioning Acceptance

1. Preserve a healthy active/idle baseline gNB and UE. Run the same-host
   heartbeat gate for at least thirty seconds with all six sources; record
   states, sequence numbers, identity, clock domain, drops, and watermarks.
2. Capture three consecutive sealed windows. Reject any unavailable or
   insufficient-evidence transition. Preserve all 21 measured features, counter
   baselines/deltas, and `ACCUMULATING -> READY -> INFERENCE_COMPLETE` lifecycle
   entries. Use Linux sampling volume even when subscriber events are zero.
3. Run the real, pinned model only after feature semantics match its evaluated
   contract. Historical availability flags represent event presence, whereas
   the new window flags represent health; reconcile this explicitly rather
   than silently scoring a changed distribution.
4. Predefine acceptable score distributions from independent normal-reference
   data. Measure each score, spread, and false-positive count. Do not require
   low values as a way to force the experiment to pass, choose a threshold after
   seeing the three windows, or retrain using held-out results.
5. The earlier 0.955 was a **real sparse-snapshot score with missing inputs
   zero-imputed**, not a synthetic fault-injection score or a measured baseline
   window score. Preserve it as evidence of the compatibility problem; there
   is no justified promise that complete-window scores will be low or stable.
6. Three windows validate plumbing, not detection efficacy. Report failures or
   high baseline scores honestly, collect a larger independent baseline for
   detection-quality evaluation, and keep all mitigation disabled.