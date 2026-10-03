# Fuzz-to-NWDAF Integration Runbook

## Ownership and Current Milestone

Keep `free5gc-security-lab` responsible for seed generation, bounded offline
parser fuzzing, reproduction, minimization, and human bug/security review.
Keep `nwdaf-research` responsible for campaign evidence linkage, passive
telemetry, held-out analytics, and analyst/response audit records.

The implemented integration includes exact-byte campaign import and a read-only
structural preflight. A reviewed NAS replay adapter, fixture verification,
run-window telemetry capture, and confirmed cleanup remain prerequisites for
the first controlled end-to-end NAS experiment. This runbook does not authorize
live replay or mitigation.

The existing `nas-afl-structured-20261002` campaign contains 48 imported seeds
and one separately recorded replay case. That replay encountered an authentication
fixture failure and has no NWDAF run bundle. Preserve it as historical evidence;
do not relabel it as a malformed-input finding or overwrite it with new trials.

## Live Observation Guard

`scripts/run_live_analytics.py` collects real read-only telemetry and checks it
against the trained feature contract. Incomplete live snapshots produce
`INSUFFICIENT_EVIDENCE` rather than a zero-imputed anomaly score. The report
lists missing, invalid, and unavailable inputs. No response is authorized by
this CLI, including when a complete vector receives an exploratory score.
Existing historical live reports remain unchanged.

## Offline Campaign Check

From the NWDAF repository root:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_input_campaign.py \
  --campaign-dir data/input_testing/nas-afl-structured-20261002
```

The command prints JSON and writes nothing. Exit code 1 means structural
blockers were found; exit code 0 means only that the inspected structural
requirements passed. It does not run free5GC, contact the testbed, train a
model, certify evidence authenticity, or grant approval.

Checks cover manifest validity and cross-references, exact corpus hashes,
normal/input-test labels in both partitions, outcomes for input-test runs,
cross-partition input-hash and recorded trial-group leakage, run JSON artifacts,
and nonempty Linux event streams. Network event counts distinguish an absent
stream (`null`) from an existing empty stream (`0`). Neither establishes that a
network collector was operational; inspect capture metadata and logs separately.
Event objects are checked for JSON structure, not full collector-schema validity.

Run the existing evaluator only after fixing structural blockers and reviewing
experimental validity. The evaluator remains a separate command; the preflight
does not replace it or change historical evaluations.

## Controlled Campaign Gates

1. **Freeze offline evidence.** Pin free5GC and harness revisions, preserve
   exact input bytes/hashes, model/prompt provenance, tool versions, resource
   budgets, repeated coverage measurements, and reproduction outputs. New
   coverage is not a reviewed bug; a crash is not a security finding.
2. **Review candidates.** Reproduce against the pinned build and an explicit
   oracle. Keep expected rejections and irreproducible observations separate.
   Minimize in a copied corpus. Any changed bytes get a new hash and case identity.
3. **Verify the fixture.** Use an isolated private testbed and synthetic IDs.
   Demonstrate successful normal registration with valid subscriber data before
   any candidate replay. Record the target revision and testbed health.
4. **Approve the adapter and run.** Require an explicit operator decision for
   each bounded selected case, target, byte hash, time/resource limit, and reset
   procedure. Implement protocol-state handling rather than treating the UE
   socket as a stateless input API. Stop on fixture failure, collector failure,
   resource-limit violation, or unverified cleanup. Do not replay an AFL queue.
5. **Collect matched trials.** Use normal registration, expected benign
   rejection, and reviewed candidate conditions with matched windows, cadence,
   background activity, and state-reset procedures. Randomize order, repeat
   trials, and verify cleanup between runs. Keep collection running for the
   actual replay interval; rolling before/after snapshots are not per-run SBI
   or PFCP event rates. Record unavailable collectors without invented rows.
6. **Freeze partitions and evaluate.** Group identical bytes and related
   mutation families together; record family identity in `trial_group` where
   applicable. Preserve whole runs within one partition. Assess duration,
   sample-count, fixture, and source-availability confounds. Freeze thresholds
   and model selection before held-out scoring. Report false positives,
   precision, recall, F1, confusion matrices, and inconclusive/negative results.
7. **Review and respond separately.** Link analyst decisions to immutable case,
   outcome, and telemetry references. Detector output is not a vulnerability
   verdict or action authorization. Any response requires separate approval,
   an allow-listed bounded action, audit evidence, and verified rollback.

Linux/SBI/free5GC signals may be relevant to early registration; PFCP activity
is not guaranteed unless session establishment reaches the SMF/UPF path. An
`input_test` label indicates exposure, not maliciousness or a confirmed anomaly.
The study measures fuzzing effectiveness, observed network distinguishability,
and workflow safety independently. End-to-end success and detector efficacy
remain unestablished until real controlled runs are collected.

## Evidence References

- [Input-testing records and evaluation](input_testing.md)
- [Offline NAS stage](fuzz_to_nwdaf_stage1.md)
- [Implementation boundary](implementation_boundary.md)
- [Existing imported campaign](../data/input_testing/nas-afl-structured-20261002/README.md)