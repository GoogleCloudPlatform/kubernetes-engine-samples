# Copyright 2025 Google LLC
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

import os
import ray
import jax

from jax.experimental import multihost_utils

ray.init()

@ray.remote(resources={"TPU": 4})
def tpu_cores():
    multihost_utils.sync_global_devices("sync")
    print(f"TPU Worker: {os.environ.get('TPU_WORKER_ID')}")
    return f"TPU cores: {jax.device_count()}"

num_workers = int(ray.available_resources()["TPU"]) // 4
print(f"Number of TPU Workers: {num_workers}")
result = [tpu_cores.remote() for _ in range(num_workers)]
print(ray.get(result))
