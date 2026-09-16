# TODOs

## Phase 1 — Dataset reconnaissance and documentation
- [x] Inspect repository state and archive contents
- [x] Verify archive structure and run count
- [x] Confirm available telemetry sources and file formats
- [x] Verify metadata, ground truth, timeline, and split manifest
- [x] Determine the first valid ML task based on actual dataset evidence
- [x] Create data/raw extraction workflow without modifying the original archive
- [x] Write data/README.md from verified facts only
- [x] Add a machine-readable schema for actual fields in the dataset

## Phase 2 — Data ingestion and validation
- [x] Implement a minimal loader for run metadata, ground truth, timeline, linux events, and split assignments
- [x] Validate missing/empty telemetry streams and record warnings clearly
- [x] Preserve run ID, timestamp, and provenance fields
- [x] Design reproducible run-level train/val/test splitting logic

## Phase 3 — Preprocessing and features
- [x] Build a preprocessing module for timestamp normalization and missing-value handling
- [x] Aggregate Linux telemetry to run-level features
- [x] Add feature provenance tracking (source -> transform -> output)
- [x] Keep all transformations reproducible and separate from raw data

## Phase 4 — Baseline ML
- [x] Train a baseline anomaly detector on run-level features
- [x] Evaluate on the provided whole-run splits
- [x] Report class-wise and overall metrics on the verified labels
- [x] Record model config, seed, and dataset version for reproducibility

## Phase 5 — NWDAF-like analytics
- [x] Wrap the best validated baseline in a research NWDAF-style API
- [x] Keep analytics model-agnostic and dataset-driven
- [x] Avoid claiming live free5GC/NWDAF integration before the offline pipeline is validated
- [x] Add the NWDAF-style run scoring pipeline and batch export workflow
- [x] Validate feature ablation on the same whole-run split to confirm the full feature set remains strongest

## Phase 6 — Agent and NEMOIR (later)
- [ ] Only implement after the analytics baseline is working
- [ ] Use structured evidence from the dataset and model outputs
- [ ] Ensure agent claims are grounded in telemetry and ground truth
- [ ] Keep NEMOIR downstream of validated analytics and evidence collection

## Guardrails
- [x] Never modify or delete the raw archive
- [x] Never fabricate telemetry, labels, or free5GC behavior
- [x] Never mix observed fact, model prediction, agent hypothesis, and NEMOIR reasoning
- [x] Keep all work dataset-first and evidence-based
