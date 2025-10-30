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

# [START gke_ai_ml_gke_ray_ray_train_maxtext_ray_trainer]
import os
from absl import app
import logging
from typing import Sequence
import ray
from ray.train.v2.api.config import ScalingConfig, RunConfig
from ray.train.v2.jax import JaxTrainer

def train_loop_per_worker(config):
    from MaxText.train import main as maxtext_main

    argv = config["argv"]
    maxtext_main(argv)

def main(argv: Sequence[str]):
    trainer = JaxTrainer(
        train_loop_per_worker=train_loop_per_worker,
        train_loop_config={"argv": argv},
        scaling_config=ScalingConfig(
            use_tpu=True,
            num_workers=4,
            topology="4x4",
            accelerator_type="TPU-V6E",
            resources_per_worker={"TPU": 4},
            placement_strategy="SPREAD",
        ),
        run_config=RunConfig(
            name="maxtext_jaxtrainer",
            worker_runtime_env={
                "env_vars": {
                    "JAX_PLATFORMS": "tpu",
                    "ENABLE_PJRT_COMPATIBILITY": "true",
                    "TPU_SLICE_BUILDER_DUMP_CHIP_FORCE": "true",
                    "TPU_SLICE_BUILDER_DUMP_ICI": "true",
                    "XLA_FLAGS": "--xla_dump_to=/tmp/xla_dump_file --xla_dump_hlo_as_proto",
                }
            },
        ),
    )
    result = trainer.fit()
    logging.info("Training complete!")
    ray.shutdown()

if __name__ == "__main__":
    app.run(main)
# [END gke_ai_ml_gke_ray_ray_train_maxtext_ray_trainer]
