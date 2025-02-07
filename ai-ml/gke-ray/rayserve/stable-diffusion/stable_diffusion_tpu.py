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

# NOTE: this file was inspired from https://github.com/ray-project/serve_config_examples/blob/master/stable_diffusion/stable_diffusion.py

"""Ray Serve Stable Diffusion example."""
from io import BytesIO
from typing import List
from fastapi import FastAPI
from fastapi.responses import Response
import logging
import ray
from ray import serve
import time

app = FastAPI()
_MAX_BATCH_SIZE = 64

logger = logging.getLogger("ray.serve")

@serve.deployment(num_replicas=1)
@serve.ingress(app)
class APIIngress:
    def __init__(self, diffusion_model_handle) -> None:
        self.handle = diffusion_model_handle

    @app.get(
        "/imagine",
        responses={200: {"content": {"image/png": {}}}},
        response_class=Response,
    )
    async def generate(self, prompt: str):
        assert len(prompt), "prompt parameter cannot be empty"

        image = await self.handle.generate.remote(prompt)
        return image


@serve.deployment(
    ray_actor_options={
        "resources": {"TPU": 4},
    },
)
class StableDiffusion:
  """FLAX Stable Diffusion Ray Serve deployment running on TPUs.

  Attributes:
    run_with_profiler: Whether or not to run with the profiler. Note that
      this saves the profile to the separate TPU VM.

  """

  def __init__(
      self, run_with_profiler: bool = False, warmup: bool = False,
      warmup_batch_size: int = _MAX_BATCH_SIZE):
    from diffusers import FlaxStableDiffusionPipeline
    from flax.jax_utils import replicate
    import jax 
    import jax.numpy as jnp
    from jax import pmap

    model_id = "CompVis/stable-diffusion-v1-4"

    self._pipeline, params = FlaxStableDiffusionPipeline.from_pretrained(
        model_id,
        revision="bf16",
        dtype=jnp.bfloat16)

    self._p_params = replicate(params)
    self._p_generate = pmap(self._pipeline._generate)
    self._run_with_profiler = run_with_profiler
    self._profiler_dir = "/tmp/tensorboard"

    if warmup:
      logger.info("Sending warmup requests.")
      warmup_prompts = ["A warmup request"] * warmup_batch_size
      self.generate_tpu(warmup_prompts)

  def generate_tpu(self, prompts: List[str]):
    """Generates a batch of images from Diffusion from a list of prompts.

    Args:
      prompts: a list of strings. Should be a factor of 4.

    Returns:
      A list of PIL Images.
    """
    from flax.training.common_utils import shard
    import jax
    import numpy as np

    rng = jax.random.PRNGKey(0)
    rng = jax.random.split(rng, jax.device_count())

    assert prompts, "prompt parameter cannot be empty"
    logger.info("Prompts: %s", prompts)
    prompt_ids = self._pipeline.prepare_inputs(prompts)
    prompt_ids = shard(prompt_ids)
    logger.info("Sharded prompt ids has shape: %s", prompt_ids.shape)
    if self._run_with_profiler:
      jax.profiler.start_trace(self._profiler_dir)

    time_start = time.time()
    images = self._p_generate(prompt_ids, self._p_params, rng)
    images = images.block_until_ready()
    elapsed = time.time() - time_start
    if self._run_with_profiler:
      jax.profiler.stop_trace()

    logger.info("Inference time (in seconds): %f", elapsed)
    logger.info("Shape of the predictions: %s", images.shape)
    images = images.reshape(
        (images.shape[0] * images.shape[1],) + images.shape[-3:])
    logger.info("Shape of images afterwards: %s", images.shape)
    return self._pipeline.numpy_to_pil(np.array(images))

  @serve.batch(batch_wait_timeout_s=10, max_batch_size=_MAX_BATCH_SIZE)
  async def batched_generate_handler(self, prompts: List[str]):
    """Sends a batch of prompts to the TPU model server.

    This takes advantage of @serve.batch, Ray Serve's built-in batching
    mechanism.

    Args:
      prompts: A list of input prompts

    Returns:
      A list of responses which contents are raw PNG.
    """
    logger.info("Number of input prompts: %d", len(prompts))
    num_to_pad = _MAX_BATCH_SIZE - len(prompts)
    prompts += ["Scratch request"] * num_to_pad

    images = self.generate_tpu(prompts)
    results = []
    for image in images[: _MAX_BATCH_SIZE - num_to_pad]:
      file_stream = BytesIO()
      image.save(file_stream, "PNG")
      results.append(
          Response(content=file_stream.getvalue(), media_type="image/png")
      )
    return results

  async def generate(self, prompt):
    return await self.batched_generate_handler(prompt)


diffusion_bound = StableDiffusion.bind()
deployment = APIIngress.bind(diffusion_bound)