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

# [START gke_ai_ml_gke_ray_rayserve_llm_torchtpu_serve_vllm_torchtpu]
import os

from ray.serve.llm import (
    LLMConfig,
    LLMServingArgs,
    ModelLoadingConfig,
    build_openai_app,
)

# Model and TPU topology configuration
MODEL_ID = os.environ.get("MODEL_ID", "google/gemma-4-26B-A4B-it")
ACCELERATOR_TYPE = os.environ.get("ACCELERATOR_TYPE", "TPU-V6E")
TPU_TOPOLOGY = os.environ.get("TPU_TOPOLOGY", "4x4")

# vLLM engine arguments and defaults
TENSOR_PARALLEL_SIZE = int(os.environ.get("TENSOR_PARALLEL_SIZE", "16"))
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "8192"))
MAX_NUM_BATCHED_TOKENS = int(os.environ.get("MAX_NUM_BATCHED_TOKENS", "4096"))

# Replica autoscaling configuration
MIN_REPLICAS = int(os.environ.get("MIN_REPLICAS", "1"))
MAX_REPLICAS = int(os.environ.get("MAX_REPLICAS", "1"))
TARGET_ONGOING_REQUESTS = int(os.environ.get("TARGET_ONGOING_REQUESTS", "32"))

llm_config = LLMConfig(
    model_loading_config=ModelLoadingConfig(
        model_id=MODEL_ID,
        model_source=MODEL_ID,
    ),
    accelerator_type=ACCELERATOR_TYPE,
    accelerator_config={
        "kind": "tpu",
        "topology": TPU_TOPOLOGY,
    },
    placement_group_config={
        "bundle_per_worker": {"TPU": 1},
    },
    deployment_config={
        "autoscaling_config": {
            "min_replicas": MIN_REPLICAS,
            "max_replicas": MAX_REPLICAS,
            "target_ongoing_requests": TARGET_ONGOING_REQUESTS,
        },
    },
    engine_kwargs={
        "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        "enable_expert_parallel": True,
        "language_model_only": True,
        "disable_hybrid_kv_cache_manager": True,
        "max_model_len": MAX_MODEL_LEN,
        "max_num_batched_tokens": MAX_NUM_BATCHED_TOKENS,
        "distributed_executor_backend": "ray",
    },
    runtime_env={
        "env_vars": {
            "TPU_MULTIHOST_BACKEND": "ray",
            # Execute Gemma 4 routed expert layers on TPU TensorCores instead of SparseCore.
            "USE_MOE_SPARSE_CORE": "0",
        }
    },
)

app = build_openai_app(LLMServingArgs(llm_configs=[llm_config]))
# [END gke_ai_ml_gke_ray_rayserve_llm_torchtpu_serve_vllm_torchtpu]
