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

# Qwen3-4B DPO-on-TPU training image.
#
# Built on the upstream vllm-tpu nightly, which ships Ray 2.56 with
# ray.train.v2.jax (JaxTrainer), qwix, flax, optax, and transformers on TPU. We
# add Tunix (post-training DPO) and grain (data loader).
#
# Protobuf note. Unlike the serve image, do not pin protobuf below 6 here. Ray
# Train does not use the proto path that breaks Ray Serve on protobuf 6, and
# Tunix's perfetto trace gencode needs protobuf 6.31 or newer. The nightly ships
# protobuf 7, which is too new for Tunix, so pin the 6.x line.
ARG BASE_IMAGE=docker.io/vllm/vllm-tpu:nightly-20260701-6af3d12-9969466
FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir \
      "protobuf>=6.31,<7" \
      "google-tunix" grain \
      wandb  # optional experiment tracking (Tunix WandbBackend)
