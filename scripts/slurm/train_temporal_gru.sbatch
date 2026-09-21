#!/usr/bin/env bash
#SBATCH --job-name=nwdaf-temporal-gru
#SBATCH --partition=MGPU-TC2
#SBATCH --gres=gpu:nvidia:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err

set -euo pipefail
repo_root="${SLURM_SUBMIT_DIR:-$PWD}"
cd "$repo_root"
result_dir="${NWDAF_GPU_RESULT_DIR:-$HOME/nwdaf-research-gpu-results}"
mkdir -p "$result_dir"
python_bin="${NWDAF_GPU_PYTHON:-$HOME/nwdaf-gpu-venv/bin/python}"
exec "$python_bin" scripts/train_temporal_gru.py \
  --output "$result_dir/temporal_gru-${SLURM_JOB_ID:-local}.json" "$@"