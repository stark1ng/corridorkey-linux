#!/usr/bin/env bash
# CorridorKey 2.0 Linux desktop — one-time setup.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
TORCH="2.9.1"
TORCHVISION="0.24.1"
CUDA_INDEX="https://download.pytorch.org/whl/cu128"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }
need git
need ffmpeg
need "$PY"

echo "==> python venv"
[ -d .venv ] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip wheel

echo "==> desktop shell dependencies"
pip install --quiet -r requirements.txt

echo "==> engine sources"
if [ ! -d CorridorKey2.0 ]; then
  git clone --depth 1 https://github.com/nikopueringer/CorridorKey2.0.git
fi
git -C CorridorKey2.0 rev-parse --short HEAD

echo "==> pytorch (CUDA 12.8 wheels)"
pip install "torch==${TORCH}" "torchvision==${TORCHVISION}" --index-url "$CUDA_INDEX"

echo "==> engine dependencies"
pip install -r CorridorKey2.0/requirements.txt

echo "==> model weights (~5 GB, downloaded once)"
if [ ! -f CorridorKey2.0/weights/corridorkey_v2.safetensors ]; then
  (cd CorridorKey2.0 && python scripts/download_weights.py)
fi

echo
echo "Ready. Start it with:  ./run.sh"
