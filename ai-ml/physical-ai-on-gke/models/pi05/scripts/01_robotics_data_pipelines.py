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
Physical AI on GKE - Phase 1: Robotics Data Pipelines
Converted from 01_robotics_data_pipelines.ipynb

Streams robotics demonstration data (LIBERO format) directly from public S3 storage
without local disk downloading, verifies dataset metadata, tests partitioning strategies,
and transforms multimodal camera feeds with Ray Data at scale.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np
import ray

# Set mandatory environment variables for anonymous public S3 streaming
# and offline HF cache guarantees.
os.environ["LEROBOT_S3_ANON"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "60"

# Add parent directory to sys.path so tools package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from tools.lerobot_datasource import LeRobotDatasource, Partitioning
from tools import cluster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("physical_ai_data_pipeline")

# Silence noisy Ray Data progress output
logging.getLogger("ray.data").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub.utils._http").setLevel(logging.ERROR)


def rename_columns(row, rename):
    return {rename.get(k, k): v for k, v in row.items()}


def transpose_images(batch, camera_keys):
    """
    Transpose images from HWC -> CHW while preserving uint8.
    Float32 conversion is deferred to GPU to avoid plasma object store memory inflation.
    """
    out = dict(batch)
    for key in camera_keys:
        out[key] = np.transpose(np.stack(list(batch[key])), (0, 3, 1, 2))
    return out


def main():
    parser = argparse.ArgumentParser(description="Run Physical AI Robotics Data Pipeline on Ray / GKE")
    default_dataset = (
        "/checkpoint/physical-ai/mirror/libero"
        if os.path.isdir("/checkpoint/physical-ai/mirror/libero")
        else "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/libero"
    )
    parser.add_argument(
        "--dataset-uri",
        default=os.environ.get("DATASET_URI", default_dataset),
        help="Local GCS mirror or public S3 URI to LeRobot v3 dataset"
    )
    parser.add_argument(
        "--storage-root",
        default=os.environ.get("STORAGE_ROOT", "/checkpoint/physical-ai"),
        help="Persistent cluster storage root (e.g. GCS FUSE mount /checkpoint)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for data transformation"
    )
    parser.add_argument(
        "--sample-rows",
        type=int,
        default=10,
        help="Number of rows to stream and inspect for validation"
    )
    args = parser.parse_args()

    # Connect to Ray cluster
    env_vars = {
        "LEROBOT_S3_ANON": "1",
        "HF_HUB_OFFLINE": "1",
        "HF_HUB_ENABLE_HF_TRANSFER": "1",
        "HF_HUB_DOWNLOAD_TIMEOUT": "60",
    }
    log.info("Connecting to Ray cluster...")
    try:
        ray.init(address="auto", ignore_reinit_error=True)
    except Exception as e:
        log.warning(f"Could not connect with address='auto' ({e}); falling back to default ray.init()...")
        ray.init(ignore_reinit_error=True)

    try:
        ray.data.DataContext.get_current().enable_progress_bars = False
    except Exception:
        pass

    log.info("Inspecting cluster topology...")
    cluster.describe(print_fn=log.info)

    # 1. Dataset metadata inspection
    log.info(f"Connecting to LeRobot datasource at {args.dataset_uri}...")
    source = LeRobotDatasource(args.dataset_uri)
    meta = source.meta

    log.info("=" * 60)
    log.info(f"Dataset Root:   {meta.root}")
    log.info(f"Episodes:       {meta.total_episodes:,}")
    log.info(f"Total Frames:   {meta.total_frames:,}")
    log.info(f"Camera Streams: {meta.video_keys}")
    log.info(f"FPS:            {meta.info.get('fps', 'N/A')}")
    state_shape = np.asarray(meta.stats['observation.state']['mean']).shape
    action_shape = np.asarray(meta.stats['action']['mean']).shape
    log.info(f"State Dim:      {state_shape}")
    log.info(f"Action Dim:     {action_shape}")
    log.info("=" * 60)

    # 2. Partitioning strategy benchmark
    log.info("Evaluating partitioning modes for distributed reading...")
    partition_plans = {}
    for mode in ("sequential", "file_group", "episode"):
        s = LeRobotDatasource(args.dataset_uri, partitioning=mode)
        plan = s.plan(parallelism=0)
        partition_plans[mode] = len(plan)
        log.info(f"  Partition mode '{mode:12s}' -> {len(plan):5d} read tasks")

    # 3. Build Ray Data pipeline
    camera_rename = {}
    image_keys = [camera_rename.get(k, k) for k in meta.video_keys]

    log.info("Constructing streaming Ray Data transform pipeline...")
    t0 = time.time()
    ds = (
        ray.data.read_datasource(source)
        .map(rename_columns, fn_args=(camera_rename,))
        .map_batches(transpose_images, batch_size=args.batch_size, fn_args=(image_keys,))
    )
    log.info(f"Pipeline defined: {ds}")

    # 4. Stream and validate sample batch
    log.info(f"Streaming validation sample ({args.sample_rows} rows)...")
    batch = ds.take_batch(args.sample_rows)
    elapsed = time.time() - t0

    sample_summary = {}
    log.info("-" * 60)
    log.info(f"Sample Batch Validated in {elapsed:.2f}s:")
    for k, v in batch.items():
        arr = np.asarray(v)
        if arr.dtype == object:
            arr = np.stack([np.asarray(x) for x in v])
        log.info(f"  {k:32s} shape={str(arr.shape):20s} dtype={arr.dtype}")
        sample_summary[k] = {
            "shape": list(arr.shape),
            "dtype": str(arr.dtype)
        }
    log.info("-" * 60)

    # 5. Save summary and preprocessed metadata to persistent storage
    storage_path = Path(args.storage_root) / "data_pipeline"
    storage_path.mkdir(parents=True, exist_ok=True)

    # Save a visual demonstration GIF from the sampled camera stream
    try:
        import imageio
        first_cam = meta.video_keys[0] if meta.video_keys else None
        if first_cam and first_cam in batch:
            cam_data = batch[first_cam]
            gif_frames = []
            for frame_arr in cam_data:
                arr = np.asarray(frame_arr)
                if arr.ndim == 3 and arr.shape[0] == 3:
                    arr = np.transpose(arr, (1, 2, 0))
                gif_frames.append(np.clip(arr, 0, 255).astype(np.uint8))
            if gif_frames:
                sample_gif_path = storage_path / "libero_stream_sample.gif"
                imageio.mimsave(str(sample_gif_path), gif_frames, duration=0.15, loop=0)
                log.info(f"Sample demonstration stream GIF saved to: {sample_gif_path}")
    except Exception as e:
        log.warning(f"Could not generate sample stream GIF: {e}")
    summary_file = storage_path / "dataset_summary.json"

    summary_data = {
        "dataset_uri": args.dataset_uri,
        "total_episodes": meta.total_episodes,
        "total_frames": meta.total_frames,
        "camera_streams": meta.video_keys,
        "state_shape": list(state_shape),
        "action_shape": list(action_shape),
        "partition_tasks": partition_plans,
        "batch_sample_shapes": sample_summary,
        "validation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
    }

    with open(summary_file, "w") as f:
        json.dump(summary_data, f, indent=2)
    log.info(f"Dataset validation summary persisted to: {summary_file}")
    log.info("Phase 1: Robotics Data Pipeline completed successfully.")


if __name__ == "__main__":
    main()
