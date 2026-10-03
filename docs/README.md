# Documentation Index

- [Synthetic anomaly demo](simulated_anomaly_demo.md): executed offline sixteen-feature training/evaluation and local simulated alerts; explicitly not real NAS research evidence.

- [Historical NAS telemetry recovery](rnas0001_retrospective_recovery.md): real time-aligned SBI/core log observations for RNAS0001, missing Linux data, and limits of retrospective reconstruction.

- [Fuzz-linked anomaly dataset](fuzz_anomaly_dataset.md): verified external case telemetry, sixteen recomputed features, independent outcome labels, grouped fresh-data evaluation, and current blockers.

- [Fuzz-case evidence check](fuzz_case_evidence_check.md): offline verification of external software/network/state/cleanup/telemetry/review references; no input replay.

## Reproduce and Run

- [Reproduction guide](reproduction.md): Python/GPU server setup and the separate Ubuntu testbed runbook.
- [GPU server audit](GPU_SERVER_AUDIT.md): inspected environment and dataset provenance.
- [Experiments](experiments.md): offline configuration comparisons and evaluator usage.
- [Fuzz-to-NWDAF Stage 1](fuzz_to_nwdaf_stage1.md): offline input-testing workflow, evidence format, and safety boundaries.
- [Fuzz-to-NWDAF integration](fuzz_to_nwdaf_integration.md): read-only campaign preflight and controlled replay/evaluation gates.
- [Window-complete telemetry](telemetry_windows.md): collector health, temporal sealing, monotonic counters, and guarded JSONL ingestion.
- [Window verification](window_verification_20261003.md): synthetic fault checks, inference lifecycle, and live collector prerequisites.
- [Operator checklist](live_telemetry_operator_checklist.md): capability/service review, monotonic heartbeat admission, and post-provisioning acceptance gates.
- [Three-source live baseline](three_source_live_baseline_20261003.md): explicit Linux/SBI/PFCP profile, three measured passive windows, and preserved failed captures.
- [Benign-control pilot plan](benign_control_plan_v1.md): prospective paired design, evidence revalidation, and model approval gates.
- [Synchronized benign pilot pair 1](benign_control_pair01_20261003.md): measured matched collection, fixed NRF receipt, and experimental limits.
- [Provenance-verified pilot pair 2](benign_control_pair02_20261003.md): reversed-order live results, parser-file hashes, and independent review checklist.
- [Analyst review workflow](analyst_review_workflow.md): hash-bound pending packets and external decision validation without automatic label promotion.
- [Scoped held-out collection](scoped_held_out_execution_20261003.md): user permission, unscored pair-5 execution, and withheld result policy.
- [Pilot completion and analysis lock](pilot_completion_20261003.md): all planned pairs collected, pending pilot reviews, and frozen non-model analysis scope.
- [Held-out benign descriptive results](benign_held_out_descriptive_20261003.md): authorized unblinding, eight verified paired endpoints, and limits on detection claims.
- [Overnight phase-4 check](fuzz_overnight_20261003.md): Slurm completion, fuzzing results, caveats, and the new seed-only NWDAF handoff.
- `scripts/import_fuzz_campaign.py`: hash-verifying importer for exact NAS fuzz seeds from `free5gc-security-lab`; creates input cases only, not replay outcomes or telemetry.
- `data/input_testing/nas-afl-structured-20261002/`: current 48-case ordinary/LLM structured-seed handoff; seed staging only, not an evaluable live campaign.
- [Offline input testing](input_testing.md): campaign record format and held-out evaluation probe.

## Methods and Evidence

- [Project method and results summary](project_method_and_results_summary.md): dataset, model/evaluation design, measured results, and limitations.
- [Measured paper results](paper_results.md): generated live-result summary; explicitly makes no causal mitigation claim.
- [Supplemental network results](supplemental_network_results.md): exploratory supplemental SBI/PFCP and multi-load findings.
- [Baseline and wrapper report](BASELINE_AND_WRAPPER_REPORT.md): baseline and integration inspection findings.
- [Injection sensitivity experiment](injection_sensitivity_experiment.md): experiment definition and interpretation boundaries.

## Prototype Boundaries and Deferred Work

- [Implementation boundary](implementation_boundary.md): capability-by-capability implementation status and evidence.
- [Phase 6 deferred](PHASE_6_DEFERRED.md): explicitly deferred agent/NemoIR work.

## Diagrams and Visual Assets

- [Workflow diagram](workflow.html): interactive pipeline overview.
- [NemoIR dashboard](nemoir_dashboard.html): prototype workflow view.
- `injection_sensitivity_preview.png`: preview asset for the injection-sensitivity experiment.

## Paper

The manuscript draft is at the repository root: [SecureNWDAF Forum 2026 draft](../SecureNWDAF_free5GC_Forum2026_12page_draft.tex). It already cites the repository in its bibliography. Its opening comments state that the prior pilot campaigns must not be presented as fresh-campaign results and that `[TBD]` results must be replaced only after new evidence is collected and validated. Cross-check every capability claim against [implementation_boundary.md](implementation_boundary.md) and every quantitative claim against its referenced result artifact. The machine-readable software citation is in [CITATION.cff](../CITATION.cff); append a DOI only after an archival release exists.

Before making the repository public, verify redistribution permission and privacy for every raw dataset, model artifact, and generated result. The Apache-2.0 license is for project software and does not establish rights to those research materials.