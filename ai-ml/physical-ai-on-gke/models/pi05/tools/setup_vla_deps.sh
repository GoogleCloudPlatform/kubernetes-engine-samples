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
if ! python3 -c "import torch" 2>/dev/null; then
    echo "=== Installing PyTorch ${TORCH_VERSION} (CUDA) ==="
    python3 -m pip install --no-cache-dir "torch==${TORCH_VERSION}" --index-url "${TORCH_CUDA_INDEX}"
fi

python3 -m pip install --no-cache-dir --no-deps lerobot==0.4.3
python3 -m pip install --no-cache-dir \
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
