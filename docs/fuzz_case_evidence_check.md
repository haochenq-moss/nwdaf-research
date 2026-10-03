# Fuzz-Case Evidence Integrity Check

This read-only checker consumes externally collected case evidence. It does
not reproduce failures, implement NAS delivery, send network traffic, repair
the prior probe, establish protocol correctness, or train/score a detector.

Create `case_evidence.json` in the evidence bundle with:

- `schema_version`: `fuzz-case-evidence-v1`.
- `input_id`, `run_id`, pinned `free5gc_commit`.
- Timezone-aware `window_start` and `window_end` for the network observation.
- `input`: an exact-byte reference with relative `path` and `sha256`.
- `stages`: references for `software_outcome`, `network_observation`,
  `protocol_state_review`, `cleanup_review`, `telemetry_bundle`, and
  `analyst_decision`. Missing stages are allowed but block completeness.

Every stage reference identifies a JSON record using relative `path` and SHA-256.
Every record repeats the same `input_id`, `run_id`, `free5gc_commit`, and
`input_sha256`, and supplies a nonempty `evidence_refs` list of supporting
relative file references and hashes. Paths must remain within the bundle.

Software/network/telemetry observations provide `window_start`, `window_end`,
and an externally observed `observed_outcome` string. The software interval may
precede the network run. Network observations must fit inside the case window;
the telemetry interval must cover that entire window.

Protocol-state, cleanup, and analyst reviews provide `reviewer_id`, timezone-aware
`reviewed_at` no earlier than network observation completion, `decision`, and
`rationale`. Only `approved` reviews satisfy this structural gate. Do not create
approval records without an actual review or treat transport closure alone as
proof of protocol cleanup.

```bash
PYTHONPATH=src .venv/bin/python scripts/check_fuzz_case_evidence.py \
  --bundle-dir /path/to/externally-collected-case-bundle
```

The command writes no artifacts. Exit zero means `REFERENCES_COMPLETE`; exit
one means `INCOMPLETE`; malformed manifests produce an argument error.
`REFERENCES_COMPLETE` verifies only identities, hashes, intervals and review
fields. It does not authenticate evidence/reviewers or validate their conclusions.
Output always leaves protocol correctness, fuzz-triggered detection, and action
authorization unestablished.

The earlier NAS campaign is still missing aligned telemetry and a verified
protocol/cleanup review. No actual fuzz-to-network chain has been completed by
adding this checker. Existing benign NRF observations are not substitutes.