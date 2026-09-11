#!/usr/bin/env bash
# Copyright 2026 Google LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

# Version of PyTorch validated for this sample on NVIDIA RTX PRO 6000 (Blackwell,
# compute capability sm_120) and Ada-class GPUs.
TORCH_VERSION="${TORCH_VERSION:-2.11.0}"
TORCH_CUDA_INDEX="${TORCH_CUDA_INDEX:-https://download.pytorch.org/whl/cu128}"

echo "=== Checking and installing VLA environment dependencies ==="

# The public rayproject/ray:*-gpu images ship the CUDA runtime but not PyTorch.
# Install it here so this sample runs on stock Ray images without a custom build.
# torchvision is installed in the SAME pip invocation so that pip resolves a
# torch/torchvision pair that is binary compatible; lerobot imports torchvision
# transitively, so training fails without it.
if ! python3 -c "import torch, torchvision" 2>/dev/null; then
    echo "=== Installing PyTorch ${TORCH_VERSION} + torchvision (CUDA) ==="
    python3 -m pip install --no-cache-dir \
        "torch==${TORCH_VERSION}" torchvision \
        --index-url "${TORCH_CUDA_INDEX}"
fi

# lerobot is installed with --no-deps to keep its pins from downgrading the
# CUDA-matched torch above, so its runtime requirements are listed explicitly
# here. Versions follow lerobot 0.4.3's own declared ranges.
#
# IMPORTANT: numpy is held at the 1.26.x that ships in the Ray image. Ray's own
# pandas/scipy/ray.data binaries are compiled against the numpy 1.x C ABI, so
# letting a transitive dependency pull numpy 2.x breaks `import ray.train` and
# `import ray.data` with "numpy.dtype size changed". opencv-python-headless
# >= 4.10 is the only dependency here that requires numpy 2, so it is capped to
# the last numpy-1-compatible release.
python3 -m pip install --no-cache-dir --no-deps lerobot==0.4.3
python3 -m pip install --no-cache-dir \
    "numpy>=1.26,<2" \
    "Pillow>=10.0" \
    "accelerate>=1.10,<2.0" \
    "einops>=0.8,<0.9" \
    "opencv-python-headless>=4.9,<4.10" \
    "termcolor>=2.4,<4" \
    "datasets>=4.0,<4.2" \
    "diffusers>=0.27.2,<0.36" \
    "draccus==0.10.0" \
    "imageio[ffmpeg]==2.37.0" \
    "av==15.1.0" \
    "num2words>=0.5,<0.6" \
    "sentencepiece==0.2.2" \
    "s3fs>=2024.1" \
    "fsspec[s3]>=2024.1" \
    "pyserial>=3.5,<4" \
    "deepdiff>=7,<9" \
    "jsonlines>=4,<5" \
    "wandb>=0.24,<0.25"

if ! python3 -c "import transformers.models.siglip.check" 2>/dev/null; then
    echo "=== Installing patched transformers fork ==="
    python3 -m pip uninstall -y transformers tokenizers || true
    if [ -f "/checkpoint/physical-ai/wheels/transformers-4.53.3-py3-none-any.whl" ]; then
        python3 -m pip install --no-cache-dir /checkpoint/physical-ai/wheels/transformers-4.53.3-py3-none-any.whl
    else
        python3 -m pip install --no-cache-dir "git+https://github.com/huggingface/transformers.git@dcddb970176382c0fcf4521b0c0e6fc15894dfe0"
    fi
fi
echo "=== VLA dependencies ready ==="
