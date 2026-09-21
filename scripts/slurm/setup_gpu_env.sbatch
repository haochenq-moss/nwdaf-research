#!/usr/bin/env bash
#SBATCH --job-name=nwdaf-gpu-setup
#SBATCH --partition=MGPU-TC2
#SBATCH --gres=gpu:nvidia:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=logs/slurm/%x-%j.out
#SBATCH --error=logs/slurm/%x-%j.err

set -euo pipefail
module load cuda/12.8.0 python312
python -m venv "$HOME/nwdaf-gpu-venv"
python -m pip install --upgrade pip
"$HOME/nwdaf-gpu-venv/bin/pip" install torch --index-url https://download.pytorch.org/whl/cu128
"$HOME/nwdaf-gpu-venv/bin/pip" install -e "$SLURM_SUBMIT_DIR"
"$HOME/nwdaf-gpu-venv/bin/python" -c 'import torch; print(torch.__version__, torch.cuda.is_available(), torch.version.cuda)'