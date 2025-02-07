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
#
import io
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
import logging
import logging.config
import asyncio
from PIL import Image
#from diffusers import StableDiffusionPipeline
import uvicorn
import time

import jax
import jax.numpy as jnp
import numpy as np
from flax.jax_utils import replicate
from jax import pmap
from jax.experimental.compilation_cache import compilation_cache as cc
from maxdiffusion import FlaxStableDiffusionXLPipeline

ROOT_LEVEL = "INFO"

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        },
    },
    "loggers": {
        "": {  # root logger
            "level": ROOT_LEVEL, #"INFO",
            "handlers": ["default"],
            "propagate": False,
        },
        "uvicorn.error": {
            "level": "DEBUG",
            "handlers": ["default"],
        },
        "uvicorn.access": {
            "level": "DEBUG",
            "handlers": ["default"],
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

LOG = logging.getLogger(__name__)
LOG.info("API is starting up")
LOG.info(uvicorn.Config.asgi_version)

app = FastAPI()
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health() -> Response:
    """Health check."""
    return Response(status_code=200)

@app.get("/")
async def read_root():
    message = f"Hello world! From FastAPI running on Uvicorn with Gunicorn."
    LOG.info(message)
    return {"message": message}
# Let's cache the model compilation, so that it doesn't take as long the next time around.

# Load the Stable Diffusion model
cc.initialize_cache("~/jax_cache")

NUM_DEVICES = jax.device_count()
if(NUM_DEVICES>0):
   LOG.info("TPU Devices Detected:")
# 1. Let's start by downloading the model and loading it into our pipeline class
# Adhering to JAX's functional approach, the model's parameters are returned seperatetely and
# will have to be passed to the pipeline during inference
pipeline, params = FlaxStableDiffusionXLPipeline.from_pretrained(
    "stabilityai/stable-diffusion-xl-base-1.0", revision="refs/pr/95", split_head_dim=True
)
LOG.info("parameters preparation")
# 2. We cast all parameters to bfloat16 EXCEPT the scheduler which we leave in
# float32 to keep maximal precision
scheduler_state = params.pop("scheduler")
params = jax.tree_util.tree_map(lambda x: x.astype(jnp.bfloat16), params)
params["scheduler"] = scheduler_state

# 3. Next, we define the different inputs to the pipeline
default_prompt = "a colorful photo of a castle in the middle of a forest with trees and bushes, by Ismail Inceoglu, shadows, high contrast, dynamic shading, hdr, detailed vegetation, digital painting, digital drawing, detailed painting, a detailed digital painting, gothic art, featured on deviantart"
default_neg_prompt = "fog, grainy, purple"
default_seed = 33
default_guidance_scale = 5.0
default_num_steps = 40
width = 1024
height = 1024


# 4. In order to be able to compile the pipeline
# all inputs have to be tensors or strings
# Let's tokenize the prompt and negative prompt
def tokenize_prompt(prompt, neg_prompt):
    LOG.info("tokenize prompts:")
    prompt_ids = pipeline.prepare_inputs(prompt)
    neg_prompt_ids = pipeline.prepare_inputs(neg_prompt)
    return prompt_ids, neg_prompt_ids


# 5. To make full use of JAX's parallelization capabilities
# the parameters and input tensors are duplicated across devices
# To make sure every device generates a different image, we create
# different seeds for each image. The model parameters won't change
# during inference so we do not wrap them into a function
LOG.info("replicate params:")
p_params = replicate(params)


def replicate_all(prompt_ids, neg_prompt_ids, seed):
    p_prompt_ids = replicate(prompt_ids)
    p_neg_prompt_ids = replicate(neg_prompt_ids)
    rng = jax.random.PRNGKey(seed)
    rng = jax.random.split(rng, NUM_DEVICES)
    return p_prompt_ids, p_neg_prompt_ids, rng


# 6. To compile the pipeline._generate function, we must pass all parameters
# to the function and tell JAX which are static arguments, that is, arguments that
# are known at compile time and won't change. In our case, it is num_inference_steps,
# height, width and return_latents.
# Once the function is compiled, these parameters are ommited from future calls and
# cannot be changed without modifying the code and recompiling.
def aot_compile(
    prompt=default_prompt,
    negative_prompt=default_neg_prompt,
    seed=default_seed,
    guidance_scale=default_guidance_scale,
    num_inference_steps=default_num_steps,
):
    LOG.info("aot compiling:")
    prompt_ids, neg_prompt_ids = tokenize_prompt(prompt, negative_prompt)
    prompt_ids, neg_prompt_ids, rng = replicate_all(prompt_ids, neg_prompt_ids, seed)
    g = jnp.array([guidance_scale] * prompt_ids.shape[0], dtype=jnp.float32)
    g = g[:, None]

    return (
        pmap(pipeline._generate, static_broadcasted_argnums=[3, 4, 5, 9])
        .lower(
            prompt_ids,
            p_params,
            rng,
            num_inference_steps,  # num_inference_steps
            height,  # height
            width,  # width
            g,
            None,
            neg_prompt_ids,
            False,  # return_latents
        )
        .compile()
    )

LOG.info("start initialized comppiling")
start = time.time()
LOG.info("Compiling ...")
p_generate = aot_compile()
LOG.info(f"Compiled in {time.time() - start}")


# 7. Let's now put it all together in a generate function.
@app.post("/generate")
async def generate(request: Request):
    LOG.info("start generate image")
    data = await request.json()
    prompt = data["prompt"]
    LOG.info(prompt)
    prompt_ids, neg_prompt_ids = tokenize_prompt(prompt, default_neg_prompt)
    prompt_ids, neg_prompt_ids, rng = replicate_all(prompt_ids, neg_prompt_ids, default_seed)
    g = jnp.array([default_guidance_scale] * prompt_ids.shape[0], dtype=jnp.float32)
    g = g[:, None]
    LOG.info("call p_generate")
    images = p_generate(prompt_ids, p_params, rng, g, None, neg_prompt_ids)

    # convert the images to PIL
    images = images.reshape((images.shape[0] * images.shape[1],) + images.shape[-3:])
    images=pipeline.numpy_to_pil(np.array(images))
    buffer = io.BytesIO()
    LOG.info("Save image")
    for i, image in enumerate(images):
        if i==0:
          image.save(buffer, format="PNG")
    #await images[0].save(buffer, format="PNG")

    # Return the image as a response
    return Response(content=buffer.getvalue(), media_type="image/png")

if __name__ == "__main__":
   uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="debug")