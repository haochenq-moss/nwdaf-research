# Documentation Index

## Reproduce and Run

- [Reproduction guide](reproduction.md): Python/GPU server setup and the separate Ubuntu testbed runbook.
- [GPU server audit](GPU_SERVER_AUDIT.md): inspected environment and dataset provenance.
- [Experiments](experiments.md): offline configuration comparisons and evaluator usage.
- [Fuzz-to-NWDAF Stage 1](fuzz_to_nwdaf_stage1.md): offline input-testing workflow, evidence format, and safety boundaries.
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