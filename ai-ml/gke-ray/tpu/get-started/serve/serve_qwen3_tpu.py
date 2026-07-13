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

# [START gke_ai_ml_gke_ray_tpu_get_started_serve_qwen3_tpu]
"""Serve Qwen3-4B-Instruct-2507 on a Cloud TPU slice with Ray Serve + vLLM.

Qwen3 (`Qwen3ForCausalLM`) is in vLLM-TPU's JAX-native architecture registry
(`tpu_inference/models/jax/qwen3.py`), so it serves on the default `flax_nnx`
path: no `MODEL_IMPL_TYPE=vllm` / torchax fallback, and `JAX_PLATFORMS=tpu` is
enough (no CPU-backend workaround). It's a small (4B), text-only, ungated model,
which keeps this get-started sample simple. One `accelerator_config.topology`
field gang-schedules the workers onto a single slice.
"""
import os

from ray.serve.llm import LLMConfig, LLMServingArgs, build_openai_app

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507")
MODEL_SOURCE = os.environ.get("MODEL_SOURCE", MODEL_ID)

ACCELERATOR_TYPE = os.environ.get("ACCELERATOR_TYPE", "TPU-V6E")
TPU_TOPOLOGY = os.environ.get("TPU_TOPOLOGY", "2x4")
TENSOR_PARALLEL_SIZE = int(os.environ.get("TENSOR_PARALLEL_SIZE", "8"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "8192"))

llm_config = LLMConfig(
    model_loading_config={"model_id": MODEL_ID, "model_source": MODEL_SOURCE},
    accelerator_type=ACCELERATOR_TYPE,
    accelerator_config={"kind": "tpu", "topology": TPU_TOPOLOGY},
    engine_kwargs={
        "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        "max_model_len": MAX_MODEL_LEN,
        "distributed_executor_backend": "ray",
    },
)

deployment = build_openai_app(LLMServingArgs(llm_configs=[llm_config]))
# [END gke_ai_ml_gke_ray_tpu_get_started_serve_qwen3_tpu]
