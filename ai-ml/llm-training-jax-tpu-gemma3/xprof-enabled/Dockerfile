# Copyright 2026 Google LLC
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

FROM us-docker.pkg.dev/cloud-tpu-images/jax-ai-image/tpu:jax0.7.2-rev1
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install gemma grain equinox
RUN pip install xprof

WORKDIR /app

# Copy your training script into the container
COPY Gemma3LLMTrain.py .
