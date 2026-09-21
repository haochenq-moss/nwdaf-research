# GPU Server Audit

## Environment

| Item | Finding |
| --- | --- |
| Repository | `/home/msai/qinh0007/nwdaf-research` |
| Login-node Python | Python 3.9.19 |
| Project Python | `.venv/bin/python` is Python 3.11.16 |
| uv | uv 0.12.5 |
| Scheduler | Slurm; `sbatch` and `srun` are available |
| GPU access | Slurm allocation only; no GPU is assumed on the login node |
| Partition | `MGPU-TC2` |
| Nodes/GRES | `TC2N01-02`: 8 NVIDIA GPUs; `TC2N03-08`: 4 NVIDIA GPUs |
| Login-node CUDA/PyTorch | `nvidia-smi` unavailable; PyTorch is not installed |
| Dataset | `data/pilot_raw.tar.gz`, extracted under `data/raw` |
| Dataset hash | `8cefce33e78fecb6786895c1ce9f153937a6624d969940ea11b55b32660cfe57` |

## Ubuntu Testbed Forks

The live Ubuntu/free5GC testbed is built from:

- https://github.com/haochenq-moss/free5gc
- https://github.com/haochenq-moss/free-ran-ue

The Ubuntu startup order is:

```bash
cd ~/free5gc
./run.sh

cd ~/free5gc/webconsole
go run server.go

cd ~/free-ran-ue
./build/free-ran-ue gnb -c config/gnb.yaml

cd ~/free-ran-ue
sudo ./build/free-ran-ue ue -c config/ue.yaml
```

The WebConsole is used to create or verify the subscriber/user before UE startup.
The GPU server consumes derived data or read-only live observations; it does not
install or recreate free5GC.

## Existing components

- Dataset extraction and run-level loader.
- Preserved whole-run split manifest: 60 train, 20 validation, 10 test.
- Linux host/process feature aggregation.
- Random Forest run-level anomaly baseline and evaluation tests.
- Offline NWDAF-style scoring wrapper (`score_run`, batch scoring, and metrics).
- Ubuntu response-agent with authenticated, bounded `tc` response and automatic
  `fq_codel` restoration.
- Supplemental real SBI/PFCP telemetry campaigns and network-feature ablations.

## Remaining boundaries

- Full 3GPP NWDAF compliance is not claimed.
- Kubernetes quarantine, OVS enforcement, clean NF replacement, and UPF failover
  are not implemented in the current prototype.
- Strict least-privilege isolation for the Ubuntu user remains a deployment task;
  the agent action itself is allow-listed.

## Potential conflicts and constraints

- Do not run GPU-dependent commands from the login shell; submit them through Slurm.
- Do not assume the login-node Python 3.9 satisfies the project requirement. Batch jobs use the project Python 3.11 environment.
- Do not regenerate or modify the pilot archive or the Ubuntu testbed.
- PFCP, SBI, and free5GC event files in the original pilot archive are empty; a
	separate supplemental campaign now supplies real SBI/PFCP evidence and is
	documented separately from the frozen pilot results.
- The current baseline is scikit-learn CPU code. GPU acceleration must be introduced and measured explicitly; it must not be implied by the partition name.

## Recommended implementation order

1. Preserve and validate dataset provenance and the whole-run split.
2. Add versioned feature schema and provenance for the existing Linux signals.
3. Complete train/validation/test model artifacts and metrics.
4. Implement real-inference analytics and subscription APIs.
5. Add policy validation, response API, mock NF adapter, and audit events.
6. Implement closed-loop response verification using only measured metrics.
7. Add GPU-specific training or inference only where a measured workload benefits from it, submitted through Slurm.
8. Document and run B0/B1/B2 and ablation experiments.

## Validation commands

Login-node-safe checks:

```bash
uv run python -m unittest discover -s tests -v
sha256sum data/pilot_raw.tar.gz
```

GPU allocation example:

```bash
sbatch scripts/slurm/run_gpu_job.sbatch python -c "import sys; print(sys.version)"
```

The batch wrapper prints the allocated node, visible GPU devices, and Python
interpreter before running the supplied command.