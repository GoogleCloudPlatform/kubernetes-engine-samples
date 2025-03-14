# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import jax

COORDINATOR_ADDR = str(os.getenv("COORDINATOR_ADDR"))
COORDINATOR_PORT = str(os.getenv("COORDINATOR_PORT"))

def log(user_str):
  print(user_str, flush = True)

def run():
  xs = jax.numpy.ones(jax.local_device_count())
  log(xs)
  log(jax.pmap(lambda x: jax.lax.psum(x, "i"), axis_name="i")(xs))

def init_processes():
  jax.distributed.initialize(
      coordinator_address=f"{COORDINATOR_ADDR}:{COORDINATOR_PORT}",
      num_processes=int(os.getenv("NNODES")),
      process_id=int(os.getenv("NODE_RANK"))
  )

  log(
      f"JAX process {jax.process_index()}/{jax.process_count()} initialized on"
      f" {COORDINATOR_ADDR}"
  )
  log(f"JAX global devices:{jax.devices()}")
  log(f"JAX local devices:{jax.local_devices()}")
  run()

if __name__ == "__main__":
  log("Starting . . .")
  init_processes()
  log("Shutting Down . . .")