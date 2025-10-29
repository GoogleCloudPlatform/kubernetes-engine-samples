# Copyright 2025 Google LLC
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

# [START gke_ai_ml_gke_ray_ray_train_maxtext_dockerfile]
# Start from a Ray base image which includes JaxTrainer API.
# Maxtext with TPU requires Python 3.12.
FROM rayproject/ray:2.49.1-py312

USER root
RUN groupadd -r ray 2>/dev/null || true && usermod -g ray ray

RUN sudo apt-get update -y \
  && sudo apt-get install --no-install-recommends -y git \
  && sudo rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the Maxtext repo and build from source, installing TPU dependencies.
RUN git clone https://github.com/AI-Hypercomputer/maxtext.git

RUN pip install --no-cache-dir uv

RUN cd maxtext && \
    uv pip install --no-cache --system -e .[tpu] --resolution=lowest && \
    install_maxtext_github_deps

# Copy the Ray Maxtext trainer to run on the remote container.
COPY maxtext_ray_trainer.py .

RUN chown -R ray:ray .
ENV PYTHONPATH=/app/maxtext/src:/app/maxtext:/app
USER ray
# [END gke_ai_ml_gke_ray_ray_train_maxtext_dockerfile]
