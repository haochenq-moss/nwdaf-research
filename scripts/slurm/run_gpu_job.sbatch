#!/usr/bin/env bash
#SBATCH --job-name=nwdaf-gpu
#SBATCH --partition=MGPU-TC2
#SBATCH --gres=gpu:nvidia:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err

set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
mkdir -p logs/slurm

if [[ ! -x "$repo_root/.venv/bin/python" ]]; then
    echo "Project Python environment not found: $repo_root/.venv/bin/python" >&2
    exit 1
fi

export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"

echo "node=${SLURMD_NODENAME:-unknown}"
echo "job_id=${SLURM_JOB_ID:-unknown}"
echo "cuda_visible_devices=${CUDA_VISIBLE_DEVICES:-unset}"
"$repo_root/.venv/bin/python" --version

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    echo "nvidia-smi is unavailable inside this allocation" >&2
fi

if [[ "$#" -eq 0 ]]; then
    set -- "$repo_root/.venv/bin/python" -m nwdaf_research evaluate
else
    set -- "$repo_root/.venv/bin/python" "$@"
fi

exec "$@"