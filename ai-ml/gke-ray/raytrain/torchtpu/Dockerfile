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

# [START gke_ai_ml_gke_ray_raytrain_torchtpu_dockerfile]
FROM us-docker.pkg.dev/ml-oss-artifacts-transient/torch-tpu-docker-container/torch-tpu:nightly-latest

# Install Ray (Core, Dashboard, and Train) and Hugging Face libraries for fine-tuning
RUN pip install --no-cache-dir \
    "ray[default,train]==2.58.0" \
    "transformers>=5.5.0" \
    datasets
# [END gke_ai_ml_gke_ray_raytrain_torchtpu_dockerfile]
