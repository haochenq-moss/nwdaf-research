# NWDAF-like Security Analytics Prototype

This project implements the GPU-side research prototype for offline security
analytics, an experimental SBA-inspired analytics API, policy-bounded response,
controlled Mock NF adaptation, and closed-loop verification.

The architecture package provides prototype DCCF, MFAF, ADRF, SecIR, and VFL
boundaries for collection/correlation, model lifecycle, evidence persistence,
typed response workflows, and operational reporting. These are implementation
modules aligned with the paper's terminology, not claims of full 3GPP service
compliance.

The pilot dataset remains immutable, and the current evidence-backed model uses
verified Linux host/process telemetry with the preserved whole-run split. See
[docs/reproduction.md](docs/reproduction.md) and
[docs/GPU_SERVER_AUDIT.md](docs/GPU_SERVER_AUDIT.md).

Project summary and measured results are documented in
[docs/project_method_and_results_summary.md](docs/project_method_and_results_summary.md),
[docs/paper_results.md](docs/paper_results.md), and
[docs/supplemental_network_results.md](docs/supplemental_network_results.md).
The implemented-versus-future capability boundary is documented in
[docs/implementation_boundary.md](docs/implementation_boundary.md).

The latest validation suite contains 71 passing tests. The API exposes a
read-only architecture status endpoint at `/architecture/v1/status`, and the
optional GPU artifacts include a CUDA MLP and a temporal GRU run.

Optional CUDA result artifacts are written outside the repository checkout:

```text
$HOME/nwdaf-research-gpu-results/
```

The verified CUDA MLP used PyTorch `2.11.0+cu128` on CUDA 12.8 and achieved
test F1 `0.9412`. The verified temporal GRU achieved test F1 `0.8571` on the
supplemental sequence experiment.

## Testbed Repositories

The Ubuntu testbed uses these maintained forks:

- [haochenq-moss/free5gc](https://github.com/haochenq-moss/free5gc)
- [haochenq-moss/free-ran-ue](https://github.com/haochenq-moss/free-ran-ue)

The free5GC runtime stays on Ubuntu. This repository contains the GPU-side
analytics, data processing, APIs, policy engine, and response integration.

## Quick Start

See [docs/reproduction.md](docs/reproduction.md) for the complete two-machine
runbook. The short version is:

```bash
# Ubuntu testbed
git clone https://github.com/haochenq-moss/free5gc.git ~/free5gc
git clone https://github.com/haochenq-moss/free-ran-ue.git ~/free-ran-ue

cd ~/free5gc
./quick-setup.sh
make all

cd ~/free-ran-ue
make
```

Start the core first, then the WebConsole, then gNB and UE in separate Ubuntu
terminals. Do not run `ueTun0` or free5GC commands on the GPU login node.
