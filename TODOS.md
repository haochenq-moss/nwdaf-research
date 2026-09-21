# Project Status and TODOs

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

## Completed Architecture and Response
- [x] Prototype DCCF normalization/correlation module
- [x] Prototype MFAF model registry
- [x] Prototype ADRF durable evidence store
- [x] Prototype SecIR typed workflow compiler
- [x] Prototype VFL operational reporting
- [x] Non-executing evidence-grounded NemoIR workflow renderer
- [x] Policy engine, authenticated Ubuntu response-agent, audit, and replay protection
- [x] Real reversible `tc` rate-limit trial with automatic `fq_codel` restoration
- [x] Kubernetes/container, OVS, and runtime-socket read-only observers
- [x] Optional CUDA MLP and temporal GRU backends with Slurm jobs
- [x] Pilot, supplemental SBI/PFCP, multi-load, randomized-live, and GPU experiments
- [x] 71 automated tests

## Remaining Deployment-Level Work
- [ ] Kubernetes NetworkPolicy/pod quarantine enforcement
- [ ] Container-runtime socket abuse generation in a disposable runtime
- [ ] OVS flow mutation and rollback adapter
- [ ] Clean NF replacement and re-registration
- [ ] UPF failover with matched service-state verification
- [ ] Real OAM/OSS/BOSS platform integration
- [ ] Causal attack/recovery experiment with matched no-response control
- [ ] Strict dedicated response-agent service account with no broader sudo access
- [ ] Full 3GPP NWDAF conformance and interoperability testing

## Research Extensions
- [ ] Expand scenarios and unseen attack seeds
- [ ] Add load/topology conditions and collector overhead measurements
- [ ] Add calibration plots and confidence intervals to all public result tables
- [ ] Evaluate GPU/CPU cost and throughput at larger scale

## Guardrails
- [x] Never modify or delete the raw archive
- [x] Never fabricate telemetry, labels, or free5GC behavior
- [x] Never mix observed fact, model prediction, agent hypothesis, and NEMOIR reasoning
- [x] Keep all work dataset-first and evidence-based
