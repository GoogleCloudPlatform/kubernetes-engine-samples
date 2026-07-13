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

# [START gke_ai_ml_gke_ray_tpu_get_started_train_dpo_qwen3]
"""DPO fine-tune Qwen3-4B-Instruct-2507 on a TPU slice with Ray Train + Tunix.

Ray Train's `JaxTrainer` owns the TPU orchestration: it reserves the slice,
builds one worker per host, and runs `train_loop_per_worker` with the JAX
distributed runtime wired. Inside, Tunix's `DPOTrainer` does the preference
optimization: a frozen reference model, qwix LoRA on the policy, and the DPO
loss over {prompts, chosen_responses, rejected_responses}.

Qwen3 has a JAX-native Tunix implementation (`tunix/models/qwen3/`) with a
dedicated `qwen3_4b_instruct_2507()` config, so it trains natively on TPU. It's
small (4B), text-only, and ungated, a clean get-started model.

Data: the preference JSONL from ../data/prepare_preference_data.py
(HuggingFaceH4/ultrafeedback_binarized reshaped to the Tunix DPO schema).

Submit as a Ray job against the cluster head:

    ray job submit --address http://localhost:8265 --working-dir . -- \
        python train_dpo_qwen3.py \
          --data /data/ufb-dpo \
          --model-dir /data/models/qwen3-4b-2507 \
          --ckpt-dir /data/ckpts/qwen3-dpo
"""
import argparse
import os

from ray.train import RunConfig, ScalingConfig
from ray.train.v2.jax import JaxTrainer


def _select_dpo_columns(row: dict) -> dict:
    """Keeps only the three columns Tunix's DPOTrainer consumes."""
    return {
        "prompts": row["prompts"],
        "chosen_responses": row["chosen_responses"],
        "rejected_responses": row["rejected_responses"],
    }


def train_loop_per_worker(config: dict) -> None:
    """Runs the DPO training loop on one TPU worker.

    Args:
        config: Run settings (data/model/ckpt dirs, max_steps, batch_size,
            tokenizer_id, and optional wandb_project/wandb_run_name).
    """
    # Imports live in the worker fn so JAX inits in its own TPU context.
    import glob
    import json

    import grain
    import jax
    import optax
    import qwix
    from metrax import logging as metrax_logging
    from orbax import checkpoint as ocp
    from transformers import AutoTokenizer

    from tunix.models.qwen3 import model as qwen3_model_lib
    from tunix.models.qwen3 import params as params_lib
    from tunix.sft.dpo.dpo_trainer import DPOTrainer, DPOTrainingConfig
    from tunix.sft.peft_trainer import MetricsLoggerOptions

    max_steps = config["max_steps"]
    batch_size = config["batch_size"]

    # Mesh across the slice. Pure FSDP (num_devices, 1) is the safe default.
    mesh = jax.make_mesh(
        (jax.device_count(), 1),
        ("fsdp", "tp"),
        axis_types=(jax.sharding.AxisType.Auto,) * 2,
    )

    model_config = qwen3_model_lib.ModelConfig.qwen3_4b_instruct_2507()
    with mesh:
        policy = params_lib.create_model_from_safe_tensors(
            config["model_dir"], model_config, mesh
        )
        ref_model = params_lib.create_model_from_safe_tensors(
            config["model_dir"], model_config, mesh
        )

    lora_provider = qwix.LoraProvider(
        module_path=(
            ".*q_proj|.*k_proj|.*v_proj|.*o_proj|"
            ".*gate_proj|.*up_proj|.*down_proj"
        ),
        rank=16,
        alpha=32.0,
    )
    # qwix traces __call__ to find layers to wrap, so pass sample
    # inputs from get_model_input().
    lora_policy = qwix.apply_lora_to_model(
        policy, lora_provider, **policy.get_model_input()
    )

    rows = []
    for path in glob.glob(os.path.join(config["data"], "*.json")):
        with open(path) as f:
            rows.extend(json.loads(line) for line in f if line.strip())
    train_ds = (
        grain.MapDataset.source(rows)
        .map(_select_dpo_columns)
        .batch(batch_size)
    )

    optimizer = optax.chain(
        optax.clip_by_global_norm(0.1),
        optax.adamw(
            optax.schedules.warmup_cosine_decay_schedule(
                init_value=0.0,
                peak_value=3e-5,
                warmup_steps=int(0.1 * max_steps),
                decay_steps=max_steps,
            ),
            b1=0.9,
            b2=0.99,
            weight_decay=0.1,
        ),
    )

    # A stdout backend prints scalars to Ray job logs. WandB is added
    # only when --wandb-project is set.
    def _stdout_backend():
        # metrax passes extra kwargs (step, fun_name), so accept them
        # or the call breaks.
        class _StdoutBackend(metrax_logging.LoggingBackend):
            """Metrics backend that prints each scalar to stdout."""

            def log_scalar(self, event, value, **kwargs):
                step = kwargs.get("step", "")
                msg = f"[metrics] step={step} {event}={float(value):.4f}"
                print(msg, flush=True)

            def close(self):
                pass
        return _StdoutBackend()

    backend_kwargs = {"custom_backend": [_stdout_backend]}
    if config.get("wandb_project"):
        # WandB requested, so use the default backends (TensorBoard and WandB).
        backend_kwargs = {"wandb": {"project": config["wandb_project"]}}

    metrics_logging_options = MetricsLoggerOptions(
        log_dir=os.path.join(config["ckpt_dir"], "metrics"),
        project_name=config.get("wandb_project") or "qwen3-dpo",
        run_name=config.get("wandb_run_name", "qwen3-dpo"),
        backend_kwargs=backend_kwargs,
    )

    # beta is the KL penalty toward the reference.
    dpo_config = DPOTrainingConfig(
        beta=0.1,
        max_steps=max_steps,
        eval_every_n_steps=max_steps,
        max_prompt_length=192,
        max_response_length=192,
        checkpoint_root_directory=config["ckpt_dir"],
        checkpointing_options=ocp.CheckpointManagerOptions(
            save_interval_steps=max(1, max_steps // 2), max_to_keep=2
        ),
        metrics_logging_options=metrics_logging_options,
    )

    tokenizer = AutoTokenizer.from_pretrained(config["tokenizer_id"])

    trainer = DPOTrainer(
        model=lora_policy,
        ref_model=ref_model,
        optimizer=optimizer,
        training_config=dpo_config,
        tokenizer=tokenizer,
    )

    with mesh:
        trainer.train(train_ds, train_ds)  # small demo, eval on the same split


def main() -> None:
    """Launches the JaxTrainer DPO run on the TPU slice."""
    parser = argparse.ArgumentParser()
    # Paths default to the gcsfuse /data mount but gs:// URIs also work.
    parser.add_argument(
        "--data", default="/data/ufb-dpo", help="Preference JSONL dir"
    )
    parser.add_argument(
        "--model-dir",
        default="/data/models/qwen3-4b-2507",
        help="Qwen3 safetensors dir",
    )
    parser.add_argument(
        "--ckpt-dir",
        default="/data/ckpts/qwen3-dpo",
        help="Checkpoint output dir",
    )
    parser.add_argument("--tokenizer-id", default="Qwen/Qwen3-4B-Instruct-2507")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--topology", default="2x4")
    parser.add_argument("--accelerator-type", default="TPU-V6E")
    # Optional WandB. Pass --wandb-project to enable (auth via WANDB_API_KEY).
    parser.add_argument(
        "--wandb-project", default="", help="W&B project (enables logging)"
    )
    parser.add_argument("--wandb-run-name", default="qwen3-dpo")
    args = parser.parse_args()

    trainer = JaxTrainer(
        train_loop_per_worker=train_loop_per_worker,
        train_loop_config={
            "data": args.data,
            "model_dir": args.model_dir,
            "ckpt_dir": args.ckpt_dir,
            "tokenizer_id": args.tokenizer_id,
            "max_steps": args.max_steps,
            "batch_size": args.batch_size,
            "wandb_project": args.wandb_project,
            "wandb_run_name": args.wandb_run_name,
        },
        scaling_config=ScalingConfig(
            use_tpu=True,
            topology=args.topology,
            accelerator_type=args.accelerator_type,
            num_workers=1,  # one worker per host, 2x4 is a single-host slice
        ),
        run_config=RunConfig(name="qwen3-dpo"),
    )
    trainer.fit()


if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_tpu_get_started_train_dpo_qwen3]
