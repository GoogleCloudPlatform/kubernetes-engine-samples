# Copyright 2024 Google LLC
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

# NOTE: this file was inspired from: https://github.com/richardsliu/vllm/blob/rayserve/examples/rayserve_tpu.py

import os

import json
import logging
from typing import Dict, List, Optional

import ray
from fastapi import FastAPI
from ray import serve
from starlette.requests import Request
from starlette.responses import Response

from vllm import LLM, SamplingParams

logger = logging.getLogger("ray.serve")

model_id = "meta-llama/Meta-Llama-3-70B"

app = FastAPI()

@serve.deployment(name="VLLMDeployment")
@serve.ingress(app)
class VLLMDeployment:
    def __init__(
        self,
        num_tpu_chips,  
    ):
        self.llm = LLM(
            model=model_id,
            tensor_parallel_size=num_tpu_chips,
            enforce_eager=True,
        )

    @app.post("/v1/generate")
    async def generate(self, request: Request):
        request_dict = await request.json()
        prompts = request_dict.pop("prompt")
        print("Processing prompt ", prompts)
        sampling_params = SamplingParams(temperature=0.7,
                                         top_p=1.0,
                                         n=1,
                                         max_tokens=1000)

        outputs = self.llm.generate(prompts, sampling_params)
        for output in outputs:
            prompt = output.prompt
            generated_text = ""
            token_ids = []
            for completion_output in output.outputs:
                generated_text += completion_output.text
                token_ids.extend(list(completion_output.token_ids))

            print("Generated text: ", generated_text)
            ret = {
                "prompt": prompt,
                "text": generated_text,
                "token_ids": token_ids,
            }

        return Response(content=json.dumps(ret))

def get_num_tpu_chips() -> int:
    if "TPU" not in ray.cluster_resources():
        # Pass in TPU chips when the current Ray cluster resources can't be auto-detected (i.e for autoscaling).
        if os.environ.get('TPU_CHIPS') is not None:
            return int(os.environ.get('TPU_CHIPS'))
        return 0
    return int(ray.cluster_resources()["TPU"])

def build_app(cli_args: Dict[str, str]) -> serve.Application:
    """Builds the Serve app based on CLI arguments."""
    ray.init(ignore_reinit_error=True)

    # Set the model to use, defaults to Llama-3-70B.
    if 'MODEL_ID' in os.environ:
        model_id = os.environ.get('MODEL_ID')

    num_tpu_chips = get_num_tpu_chips()
    pg_resources = []
    pg_resources.append({"CPU": 1})  # for the deployment replica
    for i in range(num_tpu_chips):
        pg_resources.append({"CPU": 1, "TPU": 1})  # for the vLLM actors

    # Use PACK strategy since the deployment may use more than one TPU node.
    return VLLMDeployment.options(
        placement_group_bundles=pg_resources,
        placement_group_strategy="PACK").bind(num_tpu_chips)

model = build_app({})