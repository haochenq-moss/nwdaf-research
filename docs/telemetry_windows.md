# Window-Complete Live Telemetry

## Implemented Boundary

`live/telemetry_window.py` implements a bounded tumbling-window accumulator.
`NWDAFResearchAnalyzer.score_live_window` checks its status before training or
inference. `scripts/ingest_telemetry_window.py` consumes explicit snapshot and
seal records from JSONL. No command here sends traffic, changes the active UE,
starts a collector, or authorizes mitigation.

Existing SSH snapshots and the remote log collectors do not yet emit this
handshake contract. Do not synthesize healthy bits from file presence, empty
streams, a running process, or old log-tail counts. Remote exporter integration
and a real heartbeat-bearing collection campaign remain outstanding.

Update: the new synchronous passive adapter now provides a distinct three-source
observation-time polling contract. See the
[measured live baseline](three_source_live_baseline_20261003.md). This does not
retrofit the old collectors with kernel/network watermarks or complete the
six-source exporter deployment.

## Status Precedence

| Status | Meaning |
| --- | --- |
| `COLLECTOR_UNAVAILABLE` | A required source is missing, unhealthy, unsynced, stale, or has a heartbeat coverage gap. No vector is extracted. |
| `ACCUMULATING` | Health passes but the window is not sealed or the evaluation time is before its end. |
| `INSUFFICIENT_EVIDENCE` | Sealed evidence has missing boundaries/counters, invalid metrics, counter regressions, or insufficient event volume. |
| `READY` | The full window feature contract passes. This is not proof of anomaly-detection efficacy or action authorization. |

A source failure during a window is permanent for that window. Recovery requires
a fresh window, not deleting the failure. Equal counters are allowed: monotonic
means non-decreasing, not strictly increasing. A reset or decrease requires a
new baseline and window. Invalid/missing counters never become zero.

## Exporter Contract

All six primary sources are required for this full model contract: `linux`,
`process`, `sbi`, `pfcp`, `free5gc`, and `ebpf`. A reduced-source model needs its
own explicit contract; silently disabling sources in this contract is not supported.

Select `--contract linux-sbi-pfcp-v1` explicitly for the reduced 16-feature
baseline. Its required sources are Linux, SBI, and PFCP only; excluded fields
are absent. The default remains `full-six-source-v1`. A ready reduced-profile
window cannot be scored by the historical analyzer: it returns
`MODEL_NOT_APPROVED` without inference. Readiness does not approve a model.

Each snapshot carries:

- `type`: `snapshot`.
- `observed_at`: timezone-aware ISO-8601 boundary time, strictly increasing.
- `collectors`: a source-keyed object with `heartbeat_at`, boolean
  `collector_healthy`, boolean `telemetry_source_synced`, and `observed_through`.
- `counters`: all nine cumulative counter fields below, as nonnegative integers.
- `linux_sample`: finite nonnegative `load_1m`, positive `memory_total`, and
  `memory_available` between zero and total, in bytes.

`observed_through` must equal the snapshot boundary for every source. The
exporter must flush/process data through that boundary before asserting it.
Heartbeats cannot be future-dated or older than the configured timeout.
Successive snapshots must also be within that timeout to establish continuous
coverage. Default timeout is two seconds; choose a value consistent with the
actual sampling cadence, not merely to make a failing campaign pass.

Counter fields: `linux_event_count`, `process_event_count`, `sbi_event_count`,
`sbi_error_event_count`, `pfcp_event_count`, `pfcp_request_count`,
`pfcp_response_count`, `free5gc_event_count`, and `ebpf_event_count`.

The first snapshot must exactly match the configured start; it supplies the
counter baseline and is excluded from Linux sample aggregates. The final
snapshot must exactly match the end and carry synchronized source watermarks.
The counting interval is `(start, end]`, computed as final minus initial
cumulative counters. Linux counter increments must match the buffered samples
after the baseline; missing Linux samples cannot be concealed by larger counts.

After the final snapshot, the exporter appends:

```json
{"type": "seal", "observed_at": "2026-10-03T00:00:10Z"}
```

A seal marker is mandatory and must equal the configured end. Sealed windows
reject further snapshots and duplicate seals. The default duration is ten
seconds, default minimum Linux volume is two events, and buffer limit is 10,000
snapshots. Network minimums are zero, since legitimate idle windows exist.

## Feature Semantics

A ready window supplies all 21 trained feature names, including the 14 missing
from the previous live snapshot. Duration comes from the configured boundaries;
counts come from cumulative deltas. Linux load and memory statistics are
calculated from buffered post-baseline samples, including population standard
deviation and the mean of per-sample available-memory ratios.

Availability flags derive from verified collector coverage and equal one even
when a healthy source observed zero events. They do not derive from event
presence. This differs from historical feature-builder availability flags,
which use nonempty streams. Account for that semantic/distribution difference
before treating scores from the historical model as valid live detection.

The current model consumes counts, not message rates. Dividing a window count
by duration would yield a rate, but adding or substituting rate fields requires
an explicit feature-schema/model change. No rates are fabricated here.

## Ingestion and Scoring

From the repository root, using a real exporter-produced JSONL stream:

```bash
PYTHONPATH=src .venv/bin/python scripts/ingest_telemetry_window.py \
  --snapshots /path/to/exported-window.jsonl \
  --window-start 2026-10-03T00:00:00Z \
  --as-of 2026-10-03T00:00:10Z \
  --duration-sec 10 --heartbeat-timeout-sec 2
```

The command prints its report without modifying input or writing output files.
Exit zero means `READY`; exit one means a non-ready window; malformed input
produces an argument error. Add `--score` only for exploratory inference.
Non-ready windows bypass model training/prediction. All outputs retain
`actionable: false`. Reports include timestamped `lifecycle` entries; ingestion
records readiness changes, and successful scoring appends `INFERENCE_COMPLETE`
as the top-level `status`, independently of `NORMAL`/`ANOMALY` prediction labels.
Chronological readiness checks can use `window.inspect(now)`;
sealed historical windows assess health at their end, not at the later analysis
time. That supports audit replay without mistaking old evidence for current health.

Tests use explicitly synthetic fixtures. They do not establish live collector
availability and should not be imported as experiment evidence.
See the [verification report](window_verification_20261003.md) for fault-test
coverage and the observed live-testbed blockers.