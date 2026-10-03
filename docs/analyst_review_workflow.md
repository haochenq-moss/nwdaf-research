# Analyst Review Workflow

## Pending Pilot Packets

Both live pilot pairs now have deterministic review packets, each binding 27
revalidated acquisition artifacts by SHA-256:

- [Pair 1 packet](../evaluation/analyst_review_pair01_20261003/review_packet.json):
  `PENDING`, with `legacy_missing_parser_hashes`.
- [Pair 2 packet](../evaluation/analyst_review_pair02_20261003/review_packet.json):
  `PENDING`, with `matching_parser_file_hashes`.

No independent analyst decision has been recorded. Exporting packets or passing
the automated checker is not review completion. Existing declared condition
labels, pair receipts, frozen plans, and captures remain unchanged.

Packet generation recomputes both blocks from sanitized raw captures, verifies
the stored reports/vectors/snapshot streams, checks frozen-plan identity and
pair ordering, compares fixture metadata, and recomputes the middle-window SBI
delta. The packet binds the pair journal, summary, frozen plan, and block
artifacts. It documents the receipt, evaluation grouping, and limitations.

## Human Decision

An analyst separate from the execution agent should inspect the packet's
referenced evidence and provide a new decision sidecar. The exported
`analyst_decision.draft.json` deliberately has no reviewer identity/time or
independence declaration and fails validation until genuinely completed.
Its default `inconclusive` value is an unsigned draft, not a recorded decision.

Required fields are reviewer identity, timezone-aware review time, an explicit
independence declaration, decision (`approved`, `rejected`, or `inconclusive`),
rationale, exact packet binding, and boolean review checks for:

- Artifact identity.
- Window integrity.
- Operation synchronization.
- Fixture and label basis.
- Provenance limitations.
- Background-activity limits.

Approval requires every check and valid collection/control evidence. An
inconclusive or rejected decision can retain unsatisfied checks. Pair 1's
missing historical parser hashes must be addressed explicitly, never filled
retroactively using pair 2's hashes. Review concerns benign/passive condition
evidence, not vulnerability or attack labels.

The analyst can write their completed decision to a new file, keeping the blank
draft and packet intact, then validate it against current acquisition evidence:

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_benign_pair_review.py \
  --pair-dir data/input_testing/benign-control-pilot-pair02-20261003 \
  --decision /path/to/completed-analyst-decision.json
```

Validation is read-only. It recomputes the packet binding, so stale decisions
and changed evidence fail. Reviewer identity and independence remain external
assertions: this tool does not authenticate people, verify organizational
independence, or sign records. Use the project's operator identity/audit process
for that assurance. A structurally valid decision does not approve a model,
change acquisition labels, enable mitigation, or authorize held-out execution.

## Fresh Exports

```bash
PYTHONPATH=src .venv/bin/python scripts/prepare_benign_pair_review.py \
  --pair-dir data/input_testing/benign-control-pilot-pair02-20261003 \
  --output-dir evaluation/<new-review-directory>
```

Output must be a new directory separate from acquisition evidence; existing
exports are not overwritten. Omit output/decision flags for a read-only pending
packet summary. Preserve review-sidecar hashes in the later dataset manifest,
and keep both conditions and all windows from each pair together in one split.

## Remaining Gate

The next human step is actual review of these two packets. Until then,
`label_review` remains `not_performed`. Further pilot collection may be planned,
but pilot observations must not become independently reviewed labels merely
because the runner returned `READY`. No inference, model calibration, detector
efficacy, or response evaluation is established by this workflow.