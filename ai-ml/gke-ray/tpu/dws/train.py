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

# [START gke_ai_ml_gke_ray_tpu_dws_jax_train_script]
import time
import ray
from ray import train
from ray.train import ScalingConfig
from ray.train.v2.jax import JaxTrainer
import jax
import jax.numpy as jnp

def train_func():
    # JaxTrainer handles JAX distributed setup.
    print(f"Local Devices: {jax.local_devices()}")

    # Simple Linear Regression Training Loop.
    key = jax.random.PRNGKey(0)
    x = jax.random.normal(key, (1000, 10))
    w_true = jax.random.normal(key, (10, 1))
    y = jnp.dot(x, w_true)

    # Initialize weights
    w = jnp.zeros((10, 1))
    learning_rate = 0.1

    @jax.jit
    def update(w, x, y):
        y_pred = jnp.dot(x, w)
        loss = jnp.mean((y_pred - y) ** 2)
        grad = jax.grad(lambda w: jnp.mean((jnp.dot(x, w) - y) ** 2))(w)
        return w - learning_rate * grad, loss

    # Training loop
    print("Starting training...")
    for epoch in range(50):
        w, loss = update(w, x, y)
        if epoch % 10 == 0:
            train.report({"loss": loss.item(), "epoch": epoch})
            print(f"Epoch {epoch}: Loss {loss:.4f}")

    print("Training Complete!")
    # Allow metrics to sync before closing
    time.sleep(3)

def main():
    scaling_config = ScalingConfig(
        num_workers=4,
        resources_per_worker={"TPU": 4},
        use_tpu=True,
        topology="4x4",
        accelerator_type="TPU-V6E"
    )

    trainer = JaxTrainer(
        train_loop_per_worker=train_func,
        scaling_config=scaling_config
    )

    result = trainer.fit()
    print(f"Run Result: {result.metrics}")

if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_tpu_dws_jax_train_script]