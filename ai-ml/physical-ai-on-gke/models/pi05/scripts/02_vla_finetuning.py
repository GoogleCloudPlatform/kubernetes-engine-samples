#!/usr/bin/env python3
# Copyright 2026 Google LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Physical AI on GKE - Phase 2: Distributed VLA Policy Fine-Tuning
Converted from 02_vla_finetuning.ipynb

Fine-tunes the 3.4B parameter PI0.5 Vision-Language-Action (VLA) policy using
Ray Train TorchTrainer and Distributed Data Parallel (DDP) across all GPUs on the nodepool.
Data is streamed directly via Ray Data from public S3 LeRobot storage.
Checkpoints are saved to persistent GCS storage (/checkpoint).
"""

import argparse
import io
import logging
import os
import pickle
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch
import ray
import ray.train
import ray.train.torch

# Mandatory environment flags
os.environ["LEROBOT_S3_ANON"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "60"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.lerobot_datasource import LeRobotDatasource, Partitioning
from tools import cluster, util

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("physical_ai_vla_train")


def rename_columns(row, rename):
    return {rename.get(k, k): v for k, v in row.items()}


def transpose_images(batch, camera_keys):
    out = dict(batch)
    for key in camera_keys:
        out[key] = np.transpose(np.stack(list(batch[key])), (0, 3, 1, 2))
    return out



def stage_paligemma_tokenizer():
    import os, shutil
    dst = os.path.expanduser("~/.cache/huggingface/hub")
    tok_json = os.path.join(
        dst, "models--google--paligemma-3b-pt-224/snapshots/35e4f46485b4d07967e7e9935bc3786aad50687c/tokenizer.json"
    )
    valid = False
    if os.path.exists(tok_json):
        try:
            with open(tok_json, "rb") as f:
                valid = f.read(1) == b"{"
        except Exception:
            valid = False

    if not valid:
        src_mirror = "/checkpoint/physical-ai/mirror/paligemma_tokenizer/hub"
        if os.path.isdir(src_mirror):
            log.info(f"Staging PaliGemma tokenizer from GCS mirror ({src_mirror}) -> {dst}...")
            shutil.copytree(src_mirror, dst, dirs_exist_ok=True)
            log.info("PaliGemma tokenizer cached successfully from GCS mirror.")
            return "copied_from_gcs"
        try:
            log.info("Staging PaliGemma tokenizer from S3...")
            import s3fs
            os.makedirs(dst, exist_ok=True)
            s3fs.S3FileSystem(anon=True).get(
                "anyscale-public-materials-use2/ray_summit_robotics_2026/paligemma_tokenizer/hub/",
                dst + "/",
                recursive=True,
            )
            log.info("PaliGemma tokenizer cached successfully from S3.")
            return "downloaded"
        except Exception as e:
            log.warning(f"Could not stage tokenizer: {e}")
            return f"failed: {e}"
    return "cached"


def ensure_vla_deps_on_node():
    try:
        import lerobot
        import transformers.models.siglip.check
        import serial
        return "ready"
    except ImportError:
        pass
    import subprocess
    script = "/app/tools/setup_vla_deps.sh"
    if not os.path.exists(script):
        script = "/checkpoint/physical-ai/tools/setup_vla_deps.sh"
    subprocess.run(["bash", script], check=True)
    return "installed"


def train_loop_per_worker(config):
    device = torch.device("cuda")
    ensure_vla_deps_on_node()

    # Stage the model onto this node before loading
    util.stage_model_to_local(config["model_uri"], config["model_dir"])
    util.stage_model_to_local(config["base_uri"], config["base_dir"])
    stage_paligemma_tokenizer()

    policy = util.load_pi05_policy(config["model_dir"])
    policy = ray.train.torch.prepare_model(policy)  # DDP wrap

    optimizer = torch.optim.AdamW(
        [p for p in policy.parameters() if p.requires_grad],
        lr=config.get("lr", 5e-5),
    )
    scaler = torch.amp.GradScaler("cuda")

    checkpoint = ray.train.get_checkpoint()
    start_epoch, step = (
        util.load_checkpoint(checkpoint, policy, optimizer, scaler)
        if checkpoint else (0, 0)
    )

    preprocessor, _ = util.build_preprocessor(
        policy.module.config, config["base_dir"], config["stats"], device=device,
    )

    batch_size = int(config.get("batch_size", 1))
    grad_accum = int(config.get("grad_accum", 16))
    num_epochs = int(config.get("num_epochs", 1))
    max_len = int(config.get("max_len", 512))
    max_train_steps = config.get("max_train_steps")
    num_workers = ray.train.get_context().get_world_size()
    rank = ray.train.get_context().get_world_rank()
    scheduler = util.build_lr_scheduler(optimizer, config, num_workers, last_step=step)
    shard = ray.train.get_dataset_shard("train")

    collate = util.NumpyToTorchCollate(device, image_keys=config["image_keys"])

    if util.resume_would_skip_training(start_epoch, num_epochs):
        log.warning("Resumed complete run; skipping training loop.")
        ray.train.report({
            "epoch": start_epoch - 1, "steps": step,
            "loss": float("nan"), "lr": float("nan"),
            "skipped_resumed_complete": True
        })
        return

    for epoch in range(start_epoch, num_epochs):
        optimizer.zero_grad(set_to_none=True)
        accum = 0
        loss_sum, loss_count = 0.0, 0

        for batch in shard.iter_torch_batches(batch_size=batch_size, collate_fn=collate):
            loss_val = util.train_step(policy, batch, preprocessor, max_len, grad_accum, scaler)
            step += 1
            accum += 1
            loss_sum += loss_val
            loss_count += 1

            if accum % grad_accum == 0:
                util.optimizer_step(policy, optimizer, scaler, scheduler)
                accum = 0

            if step % 10 == 0 and rank == 0:
                log.info(
                    f"epoch={epoch}  step={step}  loss={loss_val:.4f}  "
                    f"lr={scheduler.get_last_lr()[0]:.2e}  "
                    f"gpu_peak={torch.cuda.max_memory_allocated() / 1e9:.1f} GB"
                )

            if max_train_steps and step >= max_train_steps:
                break

        if accum > 0:
            util.optimizer_step(policy, optimizer, scaler, scheduler)

        avg_loss = loss_sum / max(loss_count, 1)
        metrics = {
            "epoch": epoch,
            "steps": step,
            "loss": avg_loss,
            "lr": scheduler.get_last_lr()[0],
            "gpu_peak_gb": round(torch.cuda.max_memory_allocated() / 1e9, 2),
        }

        if rank == 0:
            ckpt = util.make_checkpoint(
                policy, optimizer, scaler, epoch, step, config["stats"],
                base_model_repo=config.get("base_model_repo", "lerobot/pi05_libero_finetuned"),
                camera_rename=config.get("camera_rename", {}),
            )
            ray.train.report(metrics, checkpoint=ckpt)
        else:
            ray.train.report(metrics)

        if max_train_steps and step >= max_train_steps:
            break


def main():
    parser = argparse.ArgumentParser(description="Run VLA Fine-Tuning with Ray Train on GKE")
    default_dataset = (
        "/checkpoint/physical-ai/mirror/libero"
        if os.path.isdir("/checkpoint/physical-ai/mirror/libero")
        else "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/libero"
    )
    parser.add_argument(
        "--dataset-uri",
        default=os.environ.get("DATASET_URI", default_dataset),
        help="Path or URI to LIBERO dataset (GCS mirror or S3)"
    )
    parser.add_argument(
        "--storage-root",
        default=os.environ.get("STORAGE_ROOT", "/checkpoint/physical-ai"),
        help="Shared storage root for model staging and checkpoints"
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Number of Ray Train workers (defaults to auto-detected GPU count)"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=int(os.environ.get("MAX_TRAIN_STEPS", "50")),
        help="Max training steps (set 0 or negative for full dataset)"
    )
    parser.add_argument(
        "--round-name",
        default="round1",
        help="Training round label (e.g. round1, round2)"
    )
    args = parser.parse_args()

    max_steps = args.max_steps if args.max_steps > 0 else None

    # Connect to Ray
    log.info("Connecting to Ray cluster...")
    try:
        ray.init(address="auto", ignore_reinit_error=True)
    except Exception:
        ray.init(ignore_reinit_error=True)

    topo = cluster.describe(print_fn=log.info)
    num_train_workers = args.num_workers or cluster.train_workers()
    log.info(f"Derived Ray Train workers: {num_train_workers}")

    # Dataset Source & Stats
    source = LeRobotDatasource(args.dataset_uri)
    stats = {
        k: {"mean": v["mean"], "std": v["std"]}
        for k, v in source.meta.stats.items()
        if k in ("action", "observation.state")
    }
    camera_rename = {}
    image_keys = [camera_rename.get(k, k) for k in source.meta.video_keys]

    # Build streaming dataset
    ds = ray.data.read_datasource(source)
    if max_steps:
        # Pre-limit streaming queue so readers do not overflow plasma store
        ds = ds.limit(max_steps * 1 * num_train_workers + 32 * num_train_workers)
    train_ds = (
        ds
        .map(rename_columns, fn_args=(camera_rename,))
        .map_batches(transpose_images, batch_size=32, fn_args=(image_keys,))
    )

    # Storage paths
    cluster_storage_root = Path(args.storage_root)
    cluster_storage_root.mkdir(parents=True, exist_ok=True)

    # Clean previous run snapshot so Ray Train always executes a fresh training run
    run_dir = cluster_storage_root / f"vla-finetune-{args.round_name}"
    if run_dir.exists():
        log.info(f"Clearing previous run snapshot at {run_dir} for fresh {max_steps}-step run...")
        shutil.rmtree(run_dir, ignore_errors=True)

    mirror_root = os.environ.get("MIRROR_ROOT", "/checkpoint/physical-ai/mirror")
    if os.path.isdir(f"{mirror_root}/pi05_libero_finetuned"):
        model_uri = f"{mirror_root}/pi05_libero_finetuned"
        base_uri = f"{mirror_root}/pi05_base"
    else:
        model_uri = "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/pi05_libero_finetuned"
        base_uri = "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/pi05_base"
    local_model_dir = Path("/tmp/lerobot/pi05_libero_finetuned")
    local_base_dir = Path("/tmp/lerobot/pi05_base")

    # Ensure dependencies and stage model weights to local disk across nodes
    log.info("Ensuring VLA dependencies across all nodes...")
    util.stage_on_all_nodes(
        ray, ensure_vla_deps_on_node, "VLA Dependencies", "all nodes", log_fn=log.info
    )
    log.info("Staging model checkpoints to local storage...")
    util.stage_on_all_nodes(
        ray, lambda: util.stage_model_to_local(model_uri, local_model_dir),
        model_uri, local_model_dir, log_fn=log.info
    )
    util.stage_on_all_nodes(
        ray, lambda: util.stage_model_to_local(base_uri, local_base_dir),
        base_uri, local_base_dir, log_fn=log.info
    )
    util.stage_on_all_nodes(
        ray, stage_paligemma_tokenizer, "PaliGemma Tokenizer", "~/.cache/huggingface/hub", log_fn=log.info
    )

    # Wait for memory headroom
    util.release_phase(ray, log_fn=log.info)
    util.wait_for_host_headroom(ray, need_mib=17_000, require_all=True,
                                num_workers=num_train_workers, log_fn=log.info)

    # Launch distributed TorchTrainer
    log.info(f"Starting TorchTrainer (workers={num_train_workers}, max_steps={max_steps})...")
    trainer = ray.train.torch.TorchTrainer(
        train_loop_per_worker=train_loop_per_worker,
        train_loop_config={
            "stats": stats,
            "total_rows": source.meta.total_frames,
            "num_epochs": 1,
            "batch_size": 1,
            "grad_accum": 16,
            "lr": 5e-5,
            "warmup_frac": 0.1,
            "max_len": 512,
            "max_train_steps": max_steps,
            "image_keys": image_keys,
            "model_uri": model_uri,
            "base_uri": base_uri,
            "model_dir": local_model_dir,
            "base_dir": local_base_dir,
            "base_model_repo": "lerobot/pi05_libero_finetuned",
            "camera_rename": camera_rename,
        },
        scaling_config=ray.train.ScalingConfig(
            num_workers=num_train_workers,
            use_gpu=True,
        ),
        run_config=ray.train.RunConfig(
            name=f"vla-finetune-{args.round_name}",
            storage_path=str(cluster_storage_root),
            failure_config=ray.train.FailureConfig(max_failures=1),
            checkpoint_config=ray.train.CheckpointConfig(num_to_keep=1),
        ),
        datasets={"train": train_ds},
    )

    t0 = time.time()
    result = trainer.fit()
    duration = time.time() - t0

    # Save stable checkpoint
    checkpoint_target = cluster_storage_root / f"checkpoint_{args.round_name}" / "state.pkl"
    checkpoint_target.parent.mkdir(parents=True, exist_ok=True)
    with result.checkpoint.as_directory() as d:
        shutil.copyfile(os.path.join(d, "state.pkl"), checkpoint_target)

    log.info("=" * 60)
    log.info(f"Training completed in {duration:.1f} seconds")
    log.info(f"Checkpoint saved to: {checkpoint_target}")
    log.info(f"Final Reported Metrics: {result.metrics}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
