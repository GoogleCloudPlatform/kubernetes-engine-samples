# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-devel

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/

RUN pip3 install --no-cache-dir -r requirements.txt
RUN CUDA_HOME=/usr/local/cuda-12.1 pip3 install --no-cache-dir flash-attn --no-build-isolation

COPY custom_json_formatter.py fine_tune.py fsdp_config.yaml logging.conf /workspace/
