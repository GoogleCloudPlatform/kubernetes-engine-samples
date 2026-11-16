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

# [START gke_ai_ml_gke_ray_rayserve_llm_torchtpu_dockerfile]
FROM vllm/vllm-torchtpu:v0.32.0

ENV HF_HOME=/dev/shm/huggingface
ENV RAY_SERVE_DEFAULT_HTTP_HOST=0.0.0.0

# Install wget for KubeRay health probes and pin Ray Serve and transformers
# versions compatible with vLLM 0.29.0 and multi-host TPUs.
RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
       "ray[default,serve] @ https://s3-us-west-2.amazonaws.com/ray-wheels/master/6b2b414bb7a5b4e2705ed9f4fdab9787b92f3b08/ray-3.0.0.dev0-cp312-cp312-manylinux2014_x86_64.whl" \
       "transformers>=5.18.0"
# [END gke_ai_ml_gke_ray_rayserve_llm_torchtpu_dockerfile]
