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
Physical AI on GKE - Phase 3: Serving, Simulation Evaluation & Closed-Loop Flywheel
Converted from 03_serving_and_sim_eval.ipynb

1. Deploys the fine-tuned PI0.5 VLA policy on Ray Serve on GPU.
2. Fans out parallel Isaac Lab / physics simulation evaluation tasks across remaining GPUs.
3. Records simulation rollouts and trajectory rewards to shared storage (/checkpoint).
4. Closes the loop: filters rewarded trajectories and unions them into the training stream with Ray Data.
5. Retrains the policy (Round 2) and evaluates head-to-head reward improvement.
"""

import argparse
import glob
import json
import logging
import os
import pickle
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import requests
import torch
import ray
from ray import serve
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
from tools.lerobot_datasource import LeRobotDatasource
from tools.policy_server import PI05PolicyServer
from tools import cluster, util

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("physical_ai_serve_eval")

APP_NAME = "pi05-policy"
_SERVE_INSTANCE_IS_OURS = False


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
            log.warning(f"Failed to stage tokenizer from S3: {e}")
            return f"error: {e}"
    return "cached"


def head_ip():
    try:
        return ray.get_runtime_context().gcs_address.split(":")[0]
    except Exception:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]


def ensure_serve_clean():
    global _SERVE_INSTANCE_IS_OURS
    if _SERVE_INSTANCE_IS_OURS:
        delete_policy_app()
        return
    try:
        serve.shutdown()
    except Exception:
        pass
    _SERVE_INSTANCE_IS_OURS = True


def delete_policy_app():
    try:
        if APP_NAME in serve.status().applications:
            serve.delete(APP_NAME)
    except Exception:
        pass


def run_sim_eval(checkpoint_path, round_name, base_model_dir, storage_root,
                 sim_workers_count=1, episodes=2, max_steps=100,
                 action_horizon=10, instruction="pick up the cube and lift it"):
    """
    Deploys policy on Ray Serve, fans out simulation workers, returns collected episodes.
    """
    cluster_storage_root = Path(storage_root)
    traj_dir = cluster_storage_root / "trajectories" / round_name
    output_dir = cluster_storage_root / "rollouts" / round_name
    traj_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    ensure_serve_clean()
    util.release_phase(ray, log_fn=log.info)
    util.wait_for_host_headroom(ray, need_mib=17_000, log_fn=log.info)

    log.info(f"[{round_name}] Deploying PI05PolicyServer on Ray Serve...")
    serve.start(http_options={"host": "0.0.0.0", "port": 8000})
    serve.run(
        PI05PolicyServer.bind(
            checkpoint_path=str(checkpoint_path),
            base_model_dir=str(base_model_dir),
        ),
        name=APP_NAME,
    )
    policy_url = f"http://{head_ip()}:8000"
    log.info(f"[{round_name}] Policy server ready at {policy_url}")

    # Sanity Ping
    dummy = {
        "observation.images.image": np.zeros((256, 256, 3), dtype=np.uint8),
        "observation.images.image2": np.zeros((256, 256, 3), dtype=np.uint8),
        "observation.state": np.zeros((8,), dtype=np.float32),
        "task": instruction,
    }
    r = requests.post(f"{policy_url}/predict", data=pickle.dumps(dummy), timeout=180)
    r.raise_for_status()
    pred_action = pickle.loads(r.content)["action"]
    log.info(f"[{round_name}] Sanity check passed. Predicted action shape: {pred_action.shape}")

    # Fan out sim workers
    @ray.remote(num_gpus=0.5)
    def run_sim_task(worker_id, p_url, out_d, tr_d, cli_params):
        results_file = f"/tmp/sim_eval_{worker_id}_{round_name}.json"
        cmd = (
            f"PYTHONPATH=/app:/app/tools:$PYTHONPATH timeout 1200 python3 -u /app/tools/sim_worker.py "
            f"--worker-id {worker_id} "
            f"--policy-url {p_url} "
            f"--results-file {results_file} "
            f"--save-trajectories '{tr_d}' "
            f"{cli_params}"
        )
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, executable="/bin/bash"
        )
        try:
            with open(results_file) as f:
                results = json.load(f)
        except Exception:
            results = []
        return {
            "host": os.uname().nodename,
            "worker_id": worker_id,
            "exit_code": proc.returncode,
            "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
            "stderr_tail": "\n".join(proc.stderr.splitlines()[-10:]) if proc.returncode else "",
            "results": results,
        }

    cli_args = (
        f"--instruction '{instruction}' "
        f"--episodes {episodes} "
        f"--max-steps {max_steps} "
        f"--action-horizon {action_horizon} "
        f"--output-dir '{output_dir}' "
    )

    log.info(f"[{round_name}] Launching {sim_workers_count} sim workers x {episodes} episodes...")
    t0 = time.time()
    worker_results = ray.get([
        run_sim_task.remote(
            wi, policy_url, str(output_dir), str(traj_dir),
            cli_args + f"--seed {42 + wi * 1000}"
        )
        for wi in range(sim_workers_count)
    ])
    log.info(f"[{round_name}] Simulation evaluation completed in {time.time() - t0:.1f}s")

    # Teardown policy replica to free GPU
    delete_policy_app()
    util.release_phase(ray, log_fn=log.info)

    all_episodes = []
    for wr in worker_results:
        log.info(f"  Worker {wr['worker_id']} on {wr['host']} exited with code {wr['exit_code']}")
        for ep in wr["results"]:
            ep["round"] = round_name
            log.info(
                f"    ep{ep['episode']}: steps={ep['steps']}, "
                f"reward={ep['total_reward']:.3f}, traj={ep.get('trajectory_path', 'none')}"
            )
            all_episodes.append(ep)
        if wr["exit_code"] != 0 and wr["stderr_tail"]:
            log.warning(f"  Worker {wr['worker_id']} stderr:\n{wr['stderr_tail']}")

    return all_episodes


def compute_dataset_stats(frames):
    """Compute task-specific normalization stats from demonstration frames."""
    actions = [f["action"] for f in frames if "action" in f]
    act_arr = np.concatenate([np.atleast_2d(a) for a in actions], axis=0).astype(np.float32)
    states = [f["observation.state"] for f in frames if "observation.state" in f]
    state_arr = np.concatenate([np.atleast_2d(s) for s in states], axis=0).astype(np.float32)

    stats = {
        "action": {
            "mean": np.mean(act_arr, axis=0).astype(np.float32),
            "std": np.maximum(np.std(act_arr, axis=0), 0.05).astype(np.float32),
        },
        "observation.state": {
            "mean": np.mean(state_arr, axis=0).astype(np.float32),
            "std": np.maximum(np.std(state_arr, axis=0), 0.01).astype(np.float32),
        },
    }
    return stats


def build_mixed_dataset(libero_ds, round_name, storage_root, reward_threshold=0.0):
    """
    Load sim trajectories, filter by reward, load expert demonstrations, and build task dataset.
    """
    kept_frames = []

    # 1. Load expert demonstrations for the target manipulation task
    demo_file = Path(storage_root) / "franka_demos" / "expert_dataset.pkl"
    if demo_file.exists():
        try:
            log.info(f"Loading expert demonstrations from {demo_file}...")
            with open(demo_file, "rb") as f:
                demo_data = pickle.load(f)
            kept_frames.extend(demo_data)
            log.info(f"Loaded {len(demo_data)} expert demonstration frames for task fine-tuning.")
        except Exception as e:
            log.warning(f"Failed to load expert demonstrations: {e}")

    # 2. Filter sim trajectories (only keep successful/positive reward rollouts)
    traj_dir = Path(storage_root) / "trajectories" / round_name
    pkl_files = sorted(glob.glob(str(traj_dir / "*.pkl")))

    for path in pkl_files:
        try:
            reward = float(Path(path).stem.split("_reward")[-1])
        except Exception:
            reward = 0.0
        status = "KEEP" if reward >= reward_threshold else "DROP"
        log.info(f"  {status} {Path(path).name} (reward={reward:.3f})")
        if reward >= reward_threshold:
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                episode_frames = data if isinstance(data, list) else data.get("frames", [])
                if episode_frames:
                    chunked = util.chunk_episode_actions(episode_frames, 50)
                    for frame in chunked:
                        f_dict = dict(frame)
                        img1 = np.asarray(frame["observation.images.image"])
                        if img1.ndim == 3 and img1.shape[2] == 3:
                            f_dict["observation.images.image"] = np.transpose(img1, (2, 0, 1))
                        img2 = np.asarray(frame["observation.images.image2"])
                        if img2.ndim == 3 and img2.shape[2] == 3:
                            f_dict["observation.images.image2"] = np.transpose(img2, (2, 0, 1))
                        kept_frames.append(f_dict)
            except Exception as e:
                log.warning(f"Error loading trajectory {path}: {e}")

    if not kept_frames:
        log.warning("No demonstration or sim frames available; using base dataset.")
        return libero_ds, None

    log.info(f"Extracted {len(kept_frames)} total demonstration & sim frames for training stream.")
    # Extend 2x so streaming workers have continuous rows for multi-step training
    extended_frames = kept_frames * 2
    sim_ds = ray.data.from_items(extended_frames)
    return sim_ds, kept_frames


def train_loop_per_worker(config):
    device = torch.device("cuda")
    def _run_setup():
        script = "/app/tools/setup_vla_deps.sh"
        if not os.path.exists(script):
            script = "/checkpoint/physical-ai/tools/setup_vla_deps.sh"
        subprocess.run(["bash", script], check=True)
    try:
        import lerobot
    except ImportError:
        _run_setup()

    util.stage_model_to_local(config["model_uri"], config["model_dir"])
    util.stage_model_to_local(config["base_uri"], config["base_dir"])
    stage_paligemma_tokenizer()

    policy = util.load_pi05_policy(config["model_dir"])
    policy = ray.train.torch.prepare_model(policy)

    optimizer = torch.optim.AdamW(
        [p for p in policy.parameters() if p.requires_grad],
        lr=config.get("lr", 5e-5),
    )
    scaler = torch.amp.GradScaler("cuda")

    start_epoch, step = 0, 0
    preprocessor, _ = util.build_preprocessor(
        policy.module.config, config["base_dir"], config["stats"], device=device,
    )

    batch_size = int(config.get("batch_size", 1))
    grad_accum = int(config.get("grad_accum", 4))
    num_epochs = int(config.get("num_epochs", 1))
    max_len = int(config.get("max_len", 512))
    max_train_steps = config.get("max_train_steps", 100)
    num_workers = ray.train.get_context().get_world_size()
    rank = ray.train.get_context().get_world_rank()
    scheduler = util.build_lr_scheduler(optimizer, config, num_workers, last_step=step)
    shard = ray.train.get_dataset_shard("train")
    collate = util.NumpyToTorchCollate(device, image_keys=config["image_keys"])

    for epoch in range(num_epochs):
        loss_sum = 0.0
        loss_count = 0
        accum = 0

        for raw_batch in shard.iter_batches(batch_size=batch_size):
            step += 1
            batch = collate(raw_batch)
            loss_val = util.train_step(
                policy, batch, preprocessor, max_len, grad_accum, scaler
            )
            loss_sum += loss_val
            loss_count += 1
            accum += 1

            if accum >= grad_accum:
                util.optimizer_step(policy, optimizer, scaler, scheduler)
                accum = 0

            if step % 10 == 0:
                log.info(
                    f"[{config.get('round_name', 'round2')}] step={step} loss={loss_val:.4f} "
                    f"lr={scheduler.get_last_lr()[0]:.2e}"
                )

            if max_train_steps and step >= max_train_steps:
                break

        if accum > 0:
            util.optimizer_step(policy, optimizer, scaler, scheduler)

        metrics = {
            "epoch": epoch,
            "steps": step,
            "loss": loss_sum / max(loss_count, 1),
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


def run_training(ds, round_name, storage_root, base_model_dir, model_uri, base_uri, stats, image_keys, max_steps=100, num_workers=8):
    cluster_storage_root = Path(storage_root)
    cluster_storage_root.mkdir(parents=True, exist_ok=True)
    prior_run = cluster_storage_root / f"vla-finetune-{round_name}"
    if prior_run.exists():
        shutil.rmtree(prior_run)

    util.release_phase(ray, log_fn=log.info)
    util.wait_for_host_headroom(ray, need_mib=17_000, require_all=True, num_workers=num_workers, log_fn=log.info)

    trainer = ray.train.torch.TorchTrainer(
        train_loop_per_worker=train_loop_per_worker,
        train_loop_config={
            "round_name": round_name,
            "stats": stats,
            "batch_size": 2,
            "grad_accum": 2,
            "lr": 2e-4,
            "max_len": 512,
            "max_train_steps": max_steps,
            "image_keys": image_keys,
            "model_uri": model_uri,
            "base_uri": base_uri,
            "model_dir": str(base_model_dir),
            "base_dir": str(base_model_dir).replace("pi05_libero_finetuned", "pi05_base"),
        },
        scaling_config=ray.train.ScalingConfig(num_workers=num_workers, use_gpu=True),
        run_config=ray.train.RunConfig(
            name=f"vla-finetune-{round_name}",
            storage_path=str(cluster_storage_root),
        ),
        datasets={"train": ds},
    )
    result = trainer.fit()
    ckpt_dest = cluster_storage_root / f"checkpoint_{round_name}" / "state.pkl"
    ckpt_dest.parent.mkdir(parents=True, exist_ok=True)
    with result.checkpoint.as_directory() as d:
        shutil.copyfile(os.path.join(d, "state.pkl"), ckpt_dest)
    log.info(f"[{round_name}] Saved stable checkpoint to: {ckpt_dest}")
    return ckpt_dest, result.metrics


def main():
    parser = argparse.ArgumentParser(description="Physical AI Closed-Loop Serving and Simulation Evaluation")
    parser.add_argument(
        "--storage-root",
        default=os.environ.get("STORAGE_ROOT", "/checkpoint/physical-ai"),
        help="Storage root where checkpoints and trajectories reside"
    )
    default_dataset = (
        "/checkpoint/physical-ai/mirror/libero"
        if os.path.isdir("/checkpoint/physical-ai/mirror/libero")
        else "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/libero"
    )
    parser.add_argument(
        "--dataset-uri",
        default=os.environ.get("DATASET_URI", default_dataset),
        help="Local GCS mirror or public S3 URI to LIBERO dataset"
    )
    parser.add_argument(
        "--sim-episodes",
        type=int,
        default=2,
        help="Number of episodes per sim worker"
    )
    parser.add_argument(
        "--max-sim-steps",
        type=int,
        default=100,
        help="Max steps per sim episode"
    )
    parser.add_argument(
        "--sim-workers",
        type=int,
        default=None,
        help="Number of sim workers (default: auto-derived from cluster)"
    )
    parser.add_argument(
        "--retrain-steps",
        type=int,
        default=80,
        help="Max train steps for round 2 retraining"
    )
    args = parser.parse_args()

    # Connect to Ray
    log.info("Connecting to Ray cluster...")
    try:
        ray.init(address="auto", ignore_reinit_error=True)
    except Exception:
        ray.init(ignore_reinit_error=True)

    topo = cluster.describe(print_fn=log.info)
    sim_workers_count = args.sim_workers or cluster.sim_workers(reserve_for_serve=1)
    log.info(f"Derived Simulation Workers: {sim_workers_count}")

    storage_root = Path(args.storage_root)
    mirror_root = os.environ.get("MIRROR_ROOT", "/checkpoint/physical-ai/mirror")
    if os.path.isdir(f"{mirror_root}/pi05_libero_finetuned"):
        model_uri = f"{mirror_root}/pi05_libero_finetuned"
        base_uri = f"{mirror_root}/pi05_base"
    else:
        model_uri = "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/pi05_libero_finetuned"
        base_uri = "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/pi05_base"

    local_model_dir = Path("/tmp/lerobot/pi05_libero_finetuned")
    local_base_dir = Path("/tmp/lerobot/pi05_base")
    r1_ckpt = storage_root / "checkpoint_round1" / "state.pkl"

    # Ensure dependencies and stage model weights across all nodes
    log.info("Ensuring VLA dependencies across all nodes...")
    def _run_setup_vla():
        script = "/app/tools/setup_vla_deps.sh"
        if not os.path.exists(script):
            script = "/checkpoint/physical-ai/tools/setup_vla_deps.sh"
        return subprocess.run(
            ["bash", script],
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    util.stage_on_all_nodes(
        ray,
        _run_setup_vla,
        label="Staging VLA Dependencies",
        dest="all nodes",
        log_fn=log.info,
    )

    log.info("Staging model checkpoints to local storage...")
    util.stage_on_all_nodes(
        ray,
        lambda: util.stage_model_to_local(model_uri, local_model_dir),
        label=f"Staging {model_uri}",
        dest=str(local_model_dir),
        log_fn=log.info,
    )
    util.stage_on_all_nodes(
        ray,
        lambda: util.stage_model_to_local(base_uri, local_base_dir),
        label=f"Staging {base_uri}",
        dest=str(local_base_dir),
        log_fn=log.info,
    )

    log.info("Staging PaliGemma Tokenizer -> ~/.cache/huggingface/hub ...")
    util.stage_on_all_nodes(
        ray,
        stage_paligemma_tokenizer,
        label="Staging PaliGemma Tokenizer",
        dest="~/.cache/huggingface/hub",
        log_fn=log.info,
    )

    if not r1_ckpt.exists():
        log.warning(f"Round 1 checkpoint {r1_ckpt} not found! Staging baseline PI0.5 weights...")
        util.stage_model_to_local(model_uri, local_model_dir)
        util.stage_model_to_local(base_uri, local_base_dir)
        r1_ckpt = local_model_dir / "model.safetensors"

    # Step 1: Evaluate Round 1 Policy
    log.info("=" * 60)
    log.info("PHASE 3A: Evaluating Round 1 Policy in Simulation...")
    log.info("=" * 60)
    r1_episodes = run_sim_eval(
        checkpoint_path=r1_ckpt,
        round_name="round1",
        base_model_dir=local_model_dir,
        storage_root=args.storage_root,
        sim_workers_count=sim_workers_count,
        episodes=args.sim_episodes,
        max_steps=args.max_sim_steps,
    )

    # Step 2: Close the Flywheel - Union Rewarded Trajectories
    log.info("=" * 60)
    log.info("PHASE 3B: Closed-Loop Data Flywheel: Merging Rewarded Trajectories...")
    log.info("=" * 60)
    source = LeRobotDatasource(args.dataset_uri, action_chunk_size=50)
    camera_rename = {}
    image_keys = [camera_rename.get(k, k) for k in source.meta.video_keys]

    def rename_cols(r, ren):
        return {ren.get(k, k): v for k, v in r.items()}

    def transpose_imgs(batch, c_keys):
        out = dict(batch)
        for key in c_keys:
            out[key] = np.transpose(np.stack(list(batch[key])), (0, 3, 1, 2))
        return out

    num_train_workers = cluster.train_workers()
    base_libero_ds = (
        ray.data.read_datasource(source)
        .limit(args.retrain_steps * 1 * num_train_workers + 32 * num_train_workers)
        .map(rename_cols, fn_args=(camera_rename,))
        .map_batches(transpose_imgs, batch_size=32, fn_args=(image_keys,))
    )

    mixed_ds, kept_frames = build_mixed_dataset(base_libero_ds, "round1", args.storage_root)
    log.info(f"Flywheel Mixed Dataset: {mixed_ds}")

    # Step 3: Retrain Policy on Mixed Dataset (Round 2)
    log.info("=" * 60)
    log.info("PHASE 3C: Retraining Policy on Closed-Loop Mixed Dataset (Round 2)...")
    log.info("=" * 60)
    if kept_frames:
        stats = compute_dataset_stats(kept_frames)
        log.info("Using target task Franka dataset stats for normalization:")
        log.info(f"  action mean: {stats['action']['mean']}")
        log.info(f"  action std:  {stats['action']['std']}")
    else:
        stats = {
            k: {"mean": v["mean"], "std": v["std"]}
            for k, v in source.meta.stats.items()
            if k in ("action", "observation.state")
        }
    r2_ckpt, r2_metrics = run_training(
        ds=mixed_ds,
        round_name="round2",
        storage_root=args.storage_root,
        base_model_dir=local_model_dir,
        model_uri=model_uri,
        base_uri=base_uri,
        stats=stats,
        image_keys=image_keys,
        max_steps=args.retrain_steps,
        num_workers=num_train_workers,
    )
    log.info(f"Round 2 Retraining complete. Checkpoint: {r2_ckpt}")
    log.info(f"Round 2 Metrics: {r2_metrics}")

    # Step 4: Evaluate Round 2 Policy in Simulation
    log.info("=" * 60)
    log.info("PHASE 3D: Evaluating Round 2 Policy in Simulation (Head-to-Head)...")
    log.info("=" * 60)
    r2_episodes = run_sim_eval(
        checkpoint_path=r2_ckpt,
        round_name="round2",
        base_model_dir=local_model_dir,
        storage_root=args.storage_root,
        sim_workers_count=sim_workers_count,
        episodes=args.sim_episodes,
        max_steps=args.max_sim_steps,
    )

    # Step 5: Head-to-Head Comparison Summary
    log.info("=" * 60)
    log.info("Closed-Loop Physical AI Head-to-Head Evaluation Summary:")
    log.info("=" * 60)
    log.info(f"Round 2 Training Loss: {r2_metrics.get('loss', float('nan')):.4f}")
    log.info(f"{'Episode':<15}{'R1 Reward':>12}{'R2 Reward':>12}{'Delta':>10}")
    log.info("-" * 55)

    r1_by = {(e['worker_id'], e['episode']): e for e in r1_episodes}
    r2_by = {(e['worker_id'], e['episode']): e for e in r2_episodes}
    for key in sorted(set(r1_by) | set(r2_by)):
        a = r1_by.get(key, {}).get('total_reward', float('nan'))
        b = r2_by.get(key, {}).get('total_reward', float('nan'))
        log.info(f"{('w%d-ep%d' % key):<15}{a:>12.3f}{b:>12.3f}{(b - a):>+10.3f}")

    log.info("-" * 55)
    r1m = np.mean([e['total_reward'] for e in r1_episodes]) if r1_episodes else float('nan')
    r2m = np.mean([e['total_reward'] for e in r2_episodes]) if r2_episodes else float('nan')
    log.info(f"{'Mean':<15}{r1m:>12.3f}{r2m:>12.3f}{(r2m - r1m):>+10.3f}")
    log.info("=" * 60)
    log.info("Phase 3: Serving & Simulation Evaluation Flywheel complete.")


if __name__ == "__main__":
    main()
