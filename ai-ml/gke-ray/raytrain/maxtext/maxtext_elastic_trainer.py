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

# [START gke_ai_ml_gke_ray_ray_train_maxtext_maxtext_elastic_trainer]
import os
from absl import app
import logging
from typing import Sequence
import ray
from ray.train.v2.api.config import ScalingConfig, RunConfig, FailureConfig
from ray.train.v2.jax import JaxTrainer

def train_loop_per_worker(config):
    import maxtext
    from maxtext.trainers.pre_train.train import main as maxtext_main

    argv = config["argv"]
    maxtext_main(argv)

def main(argv: Sequence[str]):
    # Convert the config file path to an absolute path
    argv = list(argv)
    if len(argv) > 1:
        argv[1] = os.path.abspath(argv[1])

    trainer = JaxTrainer(
        train_loop_per_worker=train_loop_per_worker,
        train_loop_config={"argv": argv},
        scaling_config=ScalingConfig(
            use_tpu=True,
            # This tells Ray to scale the number of workers between 4 and 8 (i.e. 1 to 2 TPU slices).
            num_workers=(4,8),
            topology="4x4",
            accelerator_type="TPU-V6E",
            resources_per_worker={"TPU": 4},
            placement_strategy="SPREAD",
        ),
        run_config=RunConfig(
            name="maxtext_jaxtrainer",
            # Define a FailureConfig to enable fault tolerance by automatically restarting failed workers.
            failure_config=FailureConfig(max_failures=3),
            worker_runtime_env={
                "uv": {
                    # maxtext requires some additional deps
                    "packages": ["maxtext[tpu]==0.2.1"],
                    "uv_pip_install_options": ["--resolution=lowest"]
                },
            },
        ),
    )
    result = trainer.fit()
    logging.info("Training complete!")
    ray.shutdown()

if __name__ == "__main__":
    app.run(main)

# [END gke_ai_ml_gke_ray_ray_train_maxtext_maxtext_elastic_trainer]
