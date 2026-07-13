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

# Ray Serve LLM on TPU image.
#
# The vllm-tpu nightly ships protobuf 7, which is too new for Ray Serve (it
# removed FieldDescriptor.label in protobuf 6) and breaks deployment. Pin
# protobuf to 5.x, and drop grpcio-status to 1.70 to stay consistent. This is
# the smallest change that makes ray.serve.llm work on the current image.
ARG BASE_IMAGE=docker.io/vllm/vllm-tpu:nightly-20260701-6af3d12-9969466
FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir "protobuf==5.29.6" "grpcio-status==1.70.0"
