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

# NOTE: this file was inspired from: https://github.com/ray-project/ray/blob//master/doc/source/serve/doc_code/vllm_example.py

import json
import os
from typing import AsyncGenerator, Dict, List, Optional
import random

from fastapi import BackgroundTasks
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.sampling_params import SamplingParams
from vllm.utils import random_uuid

import ray
from ray import serve
from ray.serve.handle import DeploymentHandle


@serve.deployment(name="VLLMDeployment")
class VLLMDeployment:
    def __init__(self, **kwargs):
        """
        Construct a VLLM deployment.
        Refer to https://github.com/vllm-project/vllm/blob/main/vllm/engine/arg_utils.py
        for the full list of arguments.
        Args:
            model: name or path of the huggingface model to use
            download_dir: directory to download and load the weights,
                default to the default cache dir of huggingface.
            use_np_weights: save a numpy copy of model weights for
                faster loading. This can increase the disk usage by up to 2x.
            use_dummy_weights: use dummy values for model weights.
            dtype: data type for model weights and activations.
                The "auto" option will use FP16 precision
                for FP32 and FP16 models, and BF16 precision.
                for BF16 models.
            seed: random seed.
            worker_use_ray: use Ray for distributed serving, will be
                automatically set when using more than 1 GPU
            pipeline_parallel_size: number of pipeline stages.
            tensor_parallel_size: number of tensor parallel replicas.
            block_size: token block size.
            swap_space: CPU swap space size (GiB) per GPU.
            gpu_memory_utilization: the percentage of GPU memory to be used for
                the model executor
            max_num_batched_tokens: maximum number of batched tokens per iteration
            max_num_seqs: maximum number of sequences per iteration.
            disable_log_stats: disable logging statistics.
            engine_use_ray: use Ray to start the LLM engine in a separate
                process as the server process.
            disable_log_requests: disable logging requests.
        """
        args = AsyncEngineArgs(**kwargs)
        self.engine = AsyncLLMEngine.from_engine_args(args)

    async def stream_results(self, results_generator) -> AsyncGenerator[bytes, None]:
        num_returned = 0
        async for request_output in results_generator:
            text_outputs = [output.text for output in request_output.outputs]
            assert len(text_outputs) == 1
            text_output = text_outputs[0][num_returned:]
            ret = {"text": text_output}
            yield (json.dumps(ret) + "\n").encode("utf-8")
            num_returned += len(text_output)

    async def may_abort_request(self, request_id) -> None:
        await self.engine.abort(request_id)

    async def __call__(self, request_dict: dict) -> str:
        """Generate completion for the request.
        The request should be a JSON object with the following fields:
        - prompt: the prompt to use for the generation.
        - stream: whether to stream the results or not.
        - other fields: the sampling parameters (See `SamplingParams` for details).
        """
        # request_dict = await request.json()
        prompt = request_dict.pop("prompt")
        stream = request_dict.pop("stream", False)
        max_tokens = request_dict.pop("max_tokens", 1000)
        sampling_params = SamplingParams(**request_dict)
        request_id = random_uuid()
        results_generator = self.engine.generate(
            prompt, sampling_params, request_id)
        if stream:
            background_tasks = BackgroundTasks()
            # Using background_taks to abort the the request
            # if the client disconnects.
            background_tasks.add_task(self.may_abort_request, request_id)
            return StreamingResponse(
                self.stream_results(results_generator), background=background_tasks
            )

        final_output = None
        async for request_output in results_generator:
            final_output = request_output

        assert final_output is not None
        prompt = final_output.prompt
        text_outputs = [
            output.text for output in final_output.outputs]
        ret = {"text": text_outputs, "max_tokens": max_tokens}
        return json.dumps(ret)


@serve.deployment
class VLLMSummarizerDeployment:
    def __init__(self, **kwargs):
        args = AsyncEngineArgs(**kwargs)
        self.engine = AsyncLLMEngine.from_engine_args(args)

    async def __call__(self, response: str) -> str:
        """Generates summarization of a response from another model.
        The response should be a JSON object with the following fields:
        - text: the response returned from another model to summarize
        """
        request_dict = json.loads(response)
        text = request_dict.pop("text")
        prompt = f"Summarize the following text into a single sentence: {text}"
        sampling_params = SamplingParams(**request_dict)
        request_id = random_uuid()
        results_generator = self.engine.generate(
            prompt, sampling_params, request_id)

        final_output = None
        async for request_output in results_generator:
            final_output = request_output

        assert final_output is not None
        prompt = final_output.prompt
        text_outputs = [
            output.text for output in final_output.outputs]
        ret = {"text": text_outputs}
        return json.dumps(ret)


@serve.deployment
class MultiModelDeployment:
    def __init__(self, assist_model: DeploymentHandle, summarizer_model: DeploymentHandle):
        self.assistant_model = assist_model
        self.summarizer_model = summarizer_model

    async def __call__(self, request: Request) -> Response:
        model_request = await request.json()
        assistant_response = self.assistant_model.remote(model_request)
        summarizer_response = await self.summarizer_model.remote(assistant_response)
        return Response(content=summarizer_response)

def get_num_tpu_chips() -> int:
    if "TPU" not in ray.cluster_resources():
        # Pass in TPU chips when the current Ray cluster resources can't be auto-detected (i.e for autoscaling).
        if os.environ.get('TPU_CHIPS') is not None:
            return int(os.environ.get('TPU_CHIPS'))
        return 0
    return int(ray.cluster_resources()["TPU"])

def get_tpu_head() -> Optional[str]:
    if "TPU" not in ray.cluster_resources():
         # Pass in # TPU heads when the current Ray cluster resources can't be auto-detected.
        if os.environ.get('TPU_HEADS') is not None:
            return int(os.environ.get('TPU_HEADS'))
    # return the TPU-{accelerator}-head resource
    for key, _ in ray.cluster_resources().items():
        if key.endswith("head"):
            return key
    return None

def build_app(cli_args: Dict[str, str]) -> serve.Application:
    """Builds the Serve app based on CLI arguments."""
    ray.init(ignore_reinit_error=True)

    num_tpu_chips = get_num_tpu_chips()
    tpu_head = get_tpu_head()
    tpu_slices = 1
    if tpu_head is not None:
        tpu_slices = ray.cluster_resources()[tpu_head]
    num_tpu_chips_per_slice = int(num_tpu_chips/tpu_slices)
    # Construct a placement group for 1 TPU slice. Each model should run on its own slice.
    pg_resources = []
    pg_resources.append({"CPU": 1})  # for the deployment replica
    for i in range(num_tpu_chips_per_slice):
        pg_resources.append({"CPU": 1, "TPU": 1})  # for the vLLM actors
    # Add a TPU head to the placement group to ensure Ray workers are not placed across slices.
    pg_resources.append({tpu_head: 1})

    return MultiModelDeployment.bind(
        VLLMDeployment.options(
            placement_group_bundles=pg_resources,
            placement_group_strategy="PACK").bind(
            model=os.environ['ASSIST_MODEL_ID'],
            tensor_parallel_size=num_tpu_chips_per_slice,
            enforce_eager=True,
        ),
        VLLMSummarizerDeployment.options(
            placement_group_bundles=pg_resources,
            placement_group_strategy="PACK").bind(
            model=os.environ['SUMMARIZER_MODEL_ID'],
            tensor_parallel_size=num_tpu_chips_per_slice,
            enforce_eager=True,
        ),
    )

multi_model = build_app({})