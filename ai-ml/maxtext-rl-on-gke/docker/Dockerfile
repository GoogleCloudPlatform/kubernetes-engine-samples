# syntax=docker/dockerfile:1

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

ARG BASEIMAGE=python:3.12-slim-bookworm

# MaxText RL/GRPO Container for Google Cloud TPU (v7x / v6e / v5p)
# Supports both building from scratch via public GitHub or from an existing base image.
FROM ${BASEIMAGE}

ENV DEBIAN_FRONTEND=noninteractive
ENV VLLM_TARGET_DEVICE=tpu
ENV PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python
ENV VLLM_NO_USAGE_STATS=1
ENV TF_CPP_MIN_LOG_LEVEL=2
ENV UV_TORCH_BACKEND=cpu
ENV PYTHONPATH="/deps/src${PYTHONPATH:+:${PYTHONPATH}}"

# Install system dependencies, C++20 build toolchain & Google Cloud SDK
RUN apt-get update && apt-get install -y \
      curl gnupg git build-essential cmake ninja-build gcc g++ procps \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key --keyring /usr/share/keyrings/cloud.google.gpg add - \
    && apt-get update && apt-get install -y google-cloud-sdk \
    && rm -rf /var/lib/apt/lists/*

# If /deps/src does not exist in base image, clone official MaxText from public GitHub and install TPU requirements
RUN if [ ! -d "/deps/src" ]; then \
      echo ">>> Cloning official Google MaxText repository..." && \
      git clone https://github.com/google/maxtext.git /deps && \
      cd /deps && \
      python3 -m pip install -U setuptools wheel uv && \
      python3 -m uv pip install --resolution=lowest -r src/dependencies/requirements/generated_requirements/tpu-requirements.txt && \
      python3 -m uv pip install --no-deps -e .; \
    fi

# Step 1: Install extra dependencies for MaxText RL/GRPO with CPU PyTorch 2.6
RUN pip install --no-cache-dir setuptools-rust setuptools-scm wheel packaging uv cython pybind11 ninja cmake && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
      torch~=2.6.0 torchvision~=0.21.0 google-metrax perfetto kagglehub pylatexenc python-dotenv hf_transfer importlib_resources numba \
      torchax==0.0.11 tpu-info==0.7.1 setuptools==78.1.0 yapf pyzmq "runai-model-streamer[s3,gcs]" \
      cbor2 ray[default] compressed-tensors outlines_core partial-json-parser gguf xgrammar llguidance lark lm-format-enforcer diskcache \
      openai openai-harmony pybase64 python-json-logger setproctitle py-cpuinfo ijson cachetools && \
    pip uninstall -y triton

# Step 2: Download and install post-train github dependencies and vllm adapter using helper script
COPY install_deps.py /opt/install_deps.py
RUN python3 /opt/install_deps.py

# Step 3: Copy and execute standalone TPU v7 compatibility & VMEM patch script
COPY patch_tpu_v7.py /opt/patch_tpu_v7.py
RUN python3 /opt/patch_tpu_v7.py

WORKDIR /deps/src
LABEL description="MaxText GRPO RL runner optimized for Google Cloud TPU v7x, v6e, and v5p"
