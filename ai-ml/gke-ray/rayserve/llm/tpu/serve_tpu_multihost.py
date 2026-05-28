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

# [START gke_ai_ml_gke_ray_rayserve_llm_tpu_serve_tpu_multihost]
import os
import ray
from ray import serve
from ray.serve.llm import LLMConfig, ModelLoadingConfig, LLMServingArgs, build_openai_app

# Read configurations from environment variables with sensible defaults
MODEL_ID = os.environ.get("MODEL_ID", "google/gemma-4-31B-it")
MODEL_SOURCE = os.environ.get("MODEL_SOURCE", "/data/google/gemma-4-31B-it")

# Hardware options (can easily switch between TPU-V5E, TPU-V6E, etc.)
ACCELERATOR_TYPE = os.environ.get("ACCELERATOR_TYPE", "TPU-V6E")
TPU_TOPOLOGY = os.environ.get("TPU_TOPOLOGY", "4x4")

# Engine hyper-parameters (auto-converts strings to integers)
TENSOR_PARALLEL_SIZE = int(os.environ.get("TENSOR_PARALLEL_SIZE", "16"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "8192"))
MAX_NUM_BATCHED_TOKENS = int(os.environ.get("MAX_NUM_BATCHED_TOKENS", "4096"))

# Define generic multi-host TPU serving configuration
llm_config = LLMConfig(
    model_loading_config=dict(
        model_id=MODEL_ID,
        model_source=MODEL_SOURCE
    ),
    accelerator_type=ACCELERATOR_TYPE,
    accelerator_config={"kind": "tpu", "topology": TPU_TOPOLOGY},
    engine_kwargs={
        "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        "max_model_len": MAX_MODEL_LEN,
        "max_num_batched_tokens": MAX_NUM_BATCHED_TOKENS,
        "distributed_executor_backend": "ray",
    }
)

deployment = build_openai_app(
    LLMServingArgs(
        llm_configs=[llm_config]
    )
)
# [END gke_ai_ml_gke_ray_rayserve_llm_tpu_serve_tpu_multihost]
