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
import ray
from ray import serve
from ray.serve.llm import LLMConfig, ModelLoadingConfig, LLMServingArgs, build_openai_app


model_loading_config = ModelLoadingConfig(
    model_id="google/gemma-4-31B-it",
    model_source="/data/google/gemma-4-31B-it"
)

# Define multi-host TPU server configuration
llm_config = LLMConfig(
    model_loading_config=dict(
        model_id="google/gemma-4-31B-it",
        model_source="/data/google/gemma-4-31B-it"
    ),
    accelerator_type="TPU-V6E",
    accelerator_config={"kind": "tpu", "topology": "4x4"},
    engine_kwargs={
        "tensor_parallel_size": 16,
        "max_model_len": 8192,
        "max_num_batched_tokens": 4096,
        "distributed_executor_backend": "ray",
    }
)

deployment = build_openai_app(
    LLMServingArgs(
        llm_configs=[llm_config]
    )
)

# [END gke_ai_ml_gke_ray_rayserve_llm_tpu_serve_tpu_multihost]
