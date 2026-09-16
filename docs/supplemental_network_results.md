# Formal Supplemental Network-Telemetry Results

## Dataset

The Ubuntu free5GC testbed generated a separate supplemental campaign without
modifying the immutable `pilot_raw` archive:

- 120 complete runs, 0 failed runs
- 30 NORMAL, 30 S08, 30 S10, 30 S14
- 8,034 real SBI events
- 181 real PFCP events
- SHA-256: `26225fae18ee9bcbb1837159140763bf3f9c48a357bb3f4b87e0bbec881c0943`
- Scenario-stratified whole-run split: 84 train, 16 validation, 20 test

## Network-feature ablation

The test set contains one held-out run per scenario repetition. The evaluator
compares real SBI/PFCP event-count features with a combined Linux/network set.

| Feature set | Test accuracy | Test support |
| --- | ---: | ---: |
| Network-only (SBI/PFCP) | 1.0000 | 20 |
| Linux + SBI/PFCP | 1.0000 | 20 |

Both configurations produced macro precision, recall, and F1 of 1.0000 on this
supplemental test split.

## Interpretation and limits

This result establishes that real SBI/PFCP telemetry is now collected,
transferred, parsed, and usable by the feature pipeline. It does not prove that
network features generalize to arbitrary attacks: the campaign has four known
scenario classes, one load profile, short five-second runs, and a small number
of mechanisms. The perfect score may reflect strong separation between these
controlled scenario generators. It must not replace the frozen pilot result or
be presented as production accuracy.

Reproduction:

```bash
uv run python scripts/split_supplemental.py \
  --root data/supplemental_large_raw --seed 42
uv run python scripts/evaluate_supplemental_network.py \
  --root data/supplemental_large_raw \
  --split-manifest data/supplemental_large_raw/_split_manifest.json
```