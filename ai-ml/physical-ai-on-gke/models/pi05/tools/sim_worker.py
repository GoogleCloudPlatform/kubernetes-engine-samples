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
Isaac Lab Franka sim worker. Runs as a STANDALONE SUBPROCESS (not a Ray actor).

WHY subprocess and not @ray.remote actor?
Isaac Sim uses asyncio internally via omni.kit.async_engine. Inside Ray
actor threads, MainEventLoopWrapper.g_main_event_loop is None, so scene
loading crashes with `'NoneType' object has no attribute 'create_task'`.
A subprocess gives Isaac Sim a clean Python interpreter + event loop.

Communication with the Ray Serve PI0.5 deployment is via HTTP (the
subprocess can't hold a Ray DeploymentHandle from outside Ray). Ray Serve
exposes the policy at `http://HEAD:8000/predict`, and we POST a pickled obs
dict and get a pickled action chunk back.

Usage (invoked by the serving + sim-eval notebook, 03):
    python tools/sim_worker.py \
        --worker-id 0 \
        --policy-url http://10.0.18.189:8000 \
        --episodes 1 \
        --max-steps 200 \
        --action-horizon 10 \
        --output-dir /tmp/sim_rollouts \
        --seed 42
"""
import argparse
import json
import os
import pickle
import time
from typing import List

import numpy as np


def query_policy(policy_url: str, obs: dict, timeout: float = 120.0) -> dict:
    """POST obs dict to Ray Serve policy_server; get pickled action chunk back."""
    import requests
    body = pickle.dumps(obs)
    r = requests.post(
        policy_url.rstrip("/") + "/predict",
        data=body,
        headers={"Content-Type": "application/octet-stream"},
        timeout=timeout,
    )
    r.raise_for_status()
    return pickle.loads(r.content)


def save_gif(frames: List[np.ndarray], path: str, max_size: int = 256,
             colors: int = 64, fps: int = 15):
    """Save frames as a GIF, downscaled and palette-reduced to stay lightweight.

    Isaac renders full-resolution frames; embedding ~50 of them at native size
    bloats the notebook to tens of MB per GIF. Two steps keep it small:

    1. thumbnail each frame to fit `max_size`, preserving aspect ratio, and
    2. quantize to a `colors`-entry palette and let GIF frame optimization drop
       the pixels that do not change between frames.

    The rollout scene is a grey floor with a dark cube and a light arm, so 64
    colors is visually indistinguishable from truecolor and roughly halves the
    bytes: a 50-frame episode goes from about 1.4 MB to 0.7 MB, which is the
    same saving again in the notebook, since the GIF is embedded base64.
    """
    from PIL import Image
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not frames:
        return
    small = []
    for fr in frames:
        im = Image.fromarray(np.asarray(fr)[..., :3])
        im.thumbnail((max_size, max_size))
        small.append(im.convert("RGB").quantize(colors=colors,
                                                method=Image.MEDIANCUT))
    # GIF stores frame delay in centiseconds, so snap to the nearest 10 ms
    # rather than letting the encoder round for us.
    delay_ms = max(10, int(round(1000 / fps / 10)) * 10)
    small[0].save(path, save_all=True, append_images=small[1:], loop=0,
                  duration=delay_ms, optimize=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-id", type=int, default=0)
    parser.add_argument("--policy-url", default="http://127.0.0.1:8000",
                        help="Ray Serve HTTP endpoint for the policy")
    parser.add_argument("--task", default="Isaac-Lift-Cube-Franka-v0")
    parser.add_argument("--instruction",
                        default="pick up the cube and lift it")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--action-horizon", type=int, default=10,
                        help="Execute N actions from each chunk before re-querying")
    parser.add_argument("--output-dir", default="/tmp/sim_rollouts")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--headless", type=int, default=1)
    parser.add_argument("--save-frames-every", type=int, default=2)
    parser.add_argument("--results-file", default=None,
                        help="If set, write run results as JSON here")
    parser.add_argument("--save-trajectories", default=None,
                        help="If set, save (obs, action) trajectory pickles to this directory")
    args = parser.parse_args()

    print(f"[Worker-{args.worker_id}] Starting", flush=True)
    print(f"[Worker-{args.worker_id}]   policy URL: {args.policy_url}", flush=True)
    print(f"[Worker-{args.worker_id}]   task:       {args.task}", flush=True)

    # Import after argparse so usage errors don't trigger Isaac Sim boot.
    from franka_env import LiftCubeFrankaEnv

    env = LiftCubeFrankaEnv(
        task_name=args.task,
        language_instruction=args.instruction,
        headless=bool(args.headless),
        seed=args.seed,
        num_envs=1,
    )
    print(f"[Worker-{args.worker_id}] Env ready", flush=True)

    all_results = []
    for ep_idx in range(args.episodes):
        obs = env.reset()
        frames: List[np.ndarray] = []
        latencies: List[float] = []
        traj_frames: List[dict] = []   # (obs, action) pairs for trajectory saving
        policy_calls = 0

        action_chunk = None
        chunk_idx = args.action_horizon   # force first query
        action_horizon = args.action_horizon

        t_start = time.time()
        total_reward = 0.0
        step = 0

        try:
            for step in range(args.max_steps):
                if chunk_idx >= action_horizon:
                    t0 = time.time()
                    response = query_policy(args.policy_url, obs, timeout=180.0)
                    action_chunk = response["action"]
                    # n_action_steps may be smaller than --action-horizon;
                    # clamp so we don't read past the chunk.
                    chunk_n = int(response.get("n_action_steps", action_chunk.shape[0]))
                    action_horizon = min(args.action_horizon, chunk_n)
                    latencies.append(response.get("latency_ms",
                                                  (time.time() - t0) * 1000))
                    policy_calls += 1
                    chunk_idx = 0

                # Capture (obs, action) before stepping, used for trajectory saving.
                if args.save_trajectories:
                    current_action = action_chunk[min(chunk_idx, action_chunk.shape[0] - 1)].copy()
                    traj_frames.append({
                        "observation.images.image":  obs["observation.images.image"].copy(),
                        "observation.images.image2": obs["observation.images.image2"].copy(),
                        "observation.state":         obs["observation.state"].copy(),
                        "action":                    current_action.astype(np.float32),
                        "task":                      obs["task"],
                    })

                obs, reward, done, info = env.step(action_chunk, step_idx=chunk_idx)
                chunk_idx += 1
                total_reward += float(reward)

                if step % args.save_frames_every == 0:
                    try:
                        frames.append(env.render_frame())
                    except Exception as e:
                        print(f"[Worker-{args.worker_id}] render failed at step {step}: {e}",
                              flush=True)

                if done:
                    print(f"[Worker-{args.worker_id}] Episode {ep_idx} done at step {step} "
                          f"(reward={total_reward:.3f})", flush=True)
                    break
        except Exception as e:
            print(f"[Worker-{args.worker_id}] Error during episode: {type(e).__name__}: {e}",
                  flush=True)
            import traceback
            traceback.print_exc()
            # Don't re-raise; save whatever frames we got.

        episode_time = time.time() - t_start

        gif_path = os.path.join(args.output_dir,
                                f"worker{args.worker_id}_ep{ep_idx}.gif")
        if frames:
            save_gif(frames, gif_path)
            print(f"[Worker-{args.worker_id}] Saved GIF: {gif_path} "
                  f"({len(frames)} frames)", flush=True)
        else:
            gif_path = None

        # Save trajectory pickle before results JSON (same ordering as GIF/JSON
        # always write data before env.close() which can hang).
        traj_path = None
        if args.save_trajectories and traj_frames:
            os.makedirs(args.save_trajectories, exist_ok=True)
            traj_path = os.path.join(
                args.save_trajectories,
                f"worker{args.worker_id}_ep{ep_idx}_reward{total_reward:.3f}.pkl",
            )
            with open(traj_path, "wb") as f:
                pickle.dump(traj_frames, f)
            print(f"[Worker-{args.worker_id}] Saved trajectory: {traj_path} "
                  f"({len(traj_frames)} steps)", flush=True)

        result = {
            "worker_id":             args.worker_id,
            "episode":               ep_idx,
            "steps":                 step + 1,
            "policy_calls":          policy_calls,
            "episode_time_s":        episode_time,
            "avg_policy_latency_ms": float(np.mean(latencies)) if latencies else 0.0,
            "total_reward":          total_reward,
            "task":                  args.task,
            "instruction":           args.instruction,
            "gif_path":              gif_path,
            "trajectory_path":       traj_path,
        }
        all_results.append(result)

        print(f"[Worker-{args.worker_id}] Episode {ep_idx}: "
              f"{result['steps']} steps, {result['policy_calls']} calls, "
              f"{result['avg_policy_latency_ms']:.1f}ms avg latency",
              flush=True)

    # ------------------------------------------------------------
    # Write results BEFORE env.close() can hang us. Isaac Sim teardown is
    # known to deadlock under headless Ray-task subprocesses; same risk here.
    # ------------------------------------------------------------
    if args.results_file:
        os.makedirs(os.path.dirname(args.results_file) or ".", exist_ok=True)
        with open(args.results_file, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"[Worker-{args.worker_id}] Wrote results to {args.results_file}",
              flush=True)

    # ------------------------------------------------------------
    # SIGALRM force-exit on env.close() hang, a standard safeguard for
    # Isaac Sim teardown. Give it 10s, then bail.
    # ------------------------------------------------------------
    import signal
    def _force_exit(sig, frame):
        print(f"[Worker-{args.worker_id}] env.close() hung after 10s, force-exiting",
              flush=True)
        os._exit(0)
    signal.signal(signal.SIGALRM, _force_exit)
    signal.alarm(10)
    try:
        env.close()
        print(f"[Worker-{args.worker_id}] env.close() completed cleanly", flush=True)
    except Exception as e:
        print(f"[Worker-{args.worker_id}] env.close() raised: {type(e).__name__}: {e}",
              flush=True)
    os._exit(0)


if __name__ == "__main__":
    main()
