# Copyright 2026 Google LLC
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

# [START gke_ai_ml_gke_ray_rayserve_llm_tpu_dockerfile]
FROM vllm/vllm-tpu:v0.21.0

ENV VLLM_TARGET_DEVICE=tpu
ENV VLLM_XLA_CACHE_PATH=/data

USER root

RUN pip install --no-cache-dir -U \
    "https://s3-us-west-2.amazonaws.com/ray-wheels/master/75b85027a859439fae5634e49aa6443f6fbecfeb/ray-3.0.0.dev0-cp312-cp312-manylinux2014_x86_64.whl" && \
    pip install --no-cache-dir --no-deps "ray[llm]"

COPY serve_tpu_multihost.py /home/ray/serve_tpu_multihost.py
# [END gke_ai_ml_gke_ray_rayserve_llm_tpu_dockerfile]
