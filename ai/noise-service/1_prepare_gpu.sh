#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
PYTHON=${BOM_AUDIO_PYTHON:-python3.11}
command -v nvidia-smi >/dev/null || { echo "NVIDIA GPU 드라이버를 먼저 확인해주세요."; exit 2; }
nvidia-smi
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install torch==2.7.1 torchaudio==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu128
.venv/bin/python -m pip install -r audio_lab/requirements-audio.txt
.venv/bin/python verify_models.py
echo "준비 완료. bash 2_start_gpu.sh 로 시작하세요."
