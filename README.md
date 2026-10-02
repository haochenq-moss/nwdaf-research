# NWDAF-Like Security Analytics Prototype

This repository contains a research prototype for offline security analytics and bounded response workflows in a free5GC testbed. It is an external analytics system, not a 3GPP-compliant NWDAF, and does not modify or include the free5GC runtime.

The research pipeline ingests run-level telemetry, extracts features, evaluates anomaly detectors, validates policy-bounded actions, and records evidence for verification. The repository also contains prototype architecture modules aligned with DCCF, MFAF/MTLF, ADRF, SecIR, and VFL terminology. These names describe research abstractions, not standardized service implementations.

## Start Here

- [Reproduction guide](docs/reproduction.md): environment setup and the two-machine testbed runbook.
- [Method and results summary](docs/project_method_and_results_summary.md): dataset, evaluation design, measured results, and limitations.
- [Implementation boundary](docs/implementation_boundary.md): implemented, partial, and deferred capabilities.
- [Documentation index](docs/README.md): guides grouped by purpose.
- [Paper draft](SecureNWDAF_free5GC_Forum2026_12page_draft.tex): manuscript draft. Its comments identify result placeholders and campaign boundaries.
- [License](LICENSE): Apache-2.0 for the project software.
- [Citation metadata](CITATION.cff): machine-readable software citation.

## Local Setup and Tests

Requires Python 3.11 or later. With `uv` installed:

```bash
uv sync --locked
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

Putting the project virtual environment first on `PATH` ensures tests that spawn Python subprocesses use the same dependencies as the main test process. The API can be started locally with:

```bash
PYTHONPATH=src .venv/bin/uvicorn nwdaf_research.api.app:app --host 127.0.0.1 --port 8000
```

Some live and GPU workflows require the separate Ubuntu testbed, SSH credentials, Slurm, or CUDA. Do not run live stimulus or privileged response workflows as part of ordinary unit-test execution. Consult the reproduction guide and the individual script's `--help` output before running them.

## Repository Map

| Path | Purpose |
| --- | --- |
| `src/nwdaf_research/` | Analytics, ingestion, APIs, policy, adapters, observers, and workflow prototypes |
| `scripts/` | Dataset processing, evaluation, testbed orchestration, and Slurm entry points |
| `configs/` | Experiment and campaign configuration |
| `schemas/` | JSON schemas for experiment artifacts |
| `tests/` | Unit and offline regression tests |
| `data/raw/` | Preserved source telemetry and frozen split metadata |
| `data/processed/` | Derived campaign summaries and manifests |
| `data/supplemental_*_raw/` | Supplemental testbed telemetry datasets |
| `evaluation/` | Measured result artifacts referenced by reports |
| `models/` | Model artifacts and provenance manifests |
| `docs/` | Reproduction, methods, results, operations, and design boundaries |
| `SecureNWDAF_free5GC_Forum2026_12page_draft.tex` | Paper manuscript draft |

## Evidence and Data Boundaries

The pilot archive, extracted raw telemetry, and split manifest are source research artifacts. Keep them immutable when reproducing the pilot evaluation; the scripts use raw data as direct input, and results alone are not sufficient to regenerate training or evaluation. New campaigns should use a separate directory and record their configuration, hashes, splits, and run provenance.

The [measured-results report](docs/paper_results.md) explicitly limits causal claims. Live measurements are sequential or controlled trials, and B2 response experiments validate bounded execution and restoration rather than production-scale recovery. Supplemental network campaigns use controlled scenarios and should be described as exploratory. See the [method summary](docs/project_method_and_results_summary.md) and [implementation boundary](docs/implementation_boundary.md) before making paper claims.

GPU outputs may be stored outside this checkout under `$HOME/nwdaf-research-gpu-results/`; see the reproduction guide for exact artifact names and execution requirements. Secrets, local virtual environments, and transient logs should not be published.

Apache-2.0 applies to the software source code. Raw telemetry, generated evaluation data, model artifacts, and the manuscript are research materials and are not automatically relicensed by that code license; verify their provenance, redistribution rights, and privacy before making this repository public. The manuscript already includes a bibliography entry for the software. Add the archival DOI to `CITATION.cff` and the paper when a release is archived.

## Testbed Repositories

The separate Ubuntu testbed uses the maintained forks:

- [haochenq-moss/free5gc](https://github.com/haochenq-moss/free5gc)
- [haochenq-moss/free-ran-ue](https://github.com/haochenq-moss/free-ran-ue)

The GPU-side repository contains the analytics and experiment tooling. Keep testbed startup and live response procedures on the Ubuntu host, as described in [docs/reproduction.md](docs/reproduction.md).
