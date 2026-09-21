#!/usr/bin/env bash
#SBATCH --job-name=nwdaf-gpu-mlp
#SBATCH --partition=MGPU-TC2
#SBATCH --gres=gpu:nvidia:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err

set -euo pipefail
repo_root="${SLURM_SUBMIT_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$repo_root"
result_dir="${NWDaf_GPU_RESULT_DIR:-$HOME/nwdaf-research-gpu-results}"
mkdir -p "$result_dir"
python_bin="${NWDAF_GPU_PYTHON:-$HOME/nwdaf-gpu-venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
    python_bin="$repo_root/.venv/bin/python"
fi
exec "$python_bin" scripts/train_gpu_mlp.py \
	--output "$result_dir/gpu_mlp-${SLURM_JOB_ID:-local}.json" "$@"