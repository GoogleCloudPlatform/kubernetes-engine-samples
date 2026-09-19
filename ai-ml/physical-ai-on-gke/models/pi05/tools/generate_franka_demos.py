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
Generates high-quality Franka Panda pick-and-lift demonstration trajectories
for fine-tuning the Physical Intelligence PI0.5 VLA policy.

Task: "pick up the cube and lift it"
Trajectory phases:
1. Approach & Descend (steps 0-25): Moves end-effector directly toward the cube on the table.
2. Grasp (steps 25-35): Gripper fingers close firmly around the cube.
3. Lift & Hold (steps 35-100): Arm lifts the cube to z=0.20m above the table.
"""

import os
import sys
import pickle
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, "/app")
sys.path.insert(0, "/checkpoint/physical-ai")
from tools.franka_env import _MockFrankaEnv, _resize_chw_uint8, PI05_IMAGE_HW, PI05_STATE_DIM
from tools import util

def generate_expert_episode(env_seed=42, n_steps=100):
    env = _MockFrankaEnv(seed=env_seed)
    obs, _ = env.reset()

    frames = []
    total_reward = 0.0

    for step in range(n_steps):
        # Current positions
        ee = env.ee_pos.copy()
        cube = env.cube_pos.copy()

        # Action: 7-dim: [dx, dy, dz, droll, dpitch, dyaw, gripper]
        act = np.zeros(7, dtype=np.float32)

        if step < 18:
            # Phase 1: Approach & Descend to cube on table
            target = np.array([cube[0], cube[1], 0.02], dtype=np.float32)
            diff = target - ee
            act[0] = np.clip(diff[0] * 10.0, -1.0, 1.0)
            act[1] = np.clip(diff[1] * 10.0, -1.0, 1.0)
            act[2] = np.clip(diff[2] * 10.0, -1.0, 1.0)
            act[6] = -1.0  # Open gripper
        elif step < 28:
            # Phase 2: Close gripper firmly around the cube
            act[0] = 0.0
            act[1] = 0.0
            act[2] = 0.0
            act[6] = 1.0   # Close gripper firmly
        else:
            # Phase 3: Lift cube vertically to z=0.20 and hold
            target_z = 0.20
            diff_z = target_z - ee[2]
            act[0] = np.clip((cube[0] - ee[0]) * 10.0, -1.0, 1.0)
            act[1] = np.clip((cube[1] - ee[1]) * 10.0, -1.0, 1.0)
            act[2] = np.clip(diff_z * 10.0, -1.0, 1.0)
            act[6] = 1.0   # Keep gripper closed

        # Render frame
        img = env.render()
        img_resized = _resize_chw_uint8(img, hw=PI05_IMAGE_HW)

        # Extract 8-D state
        joint_state = np.zeros(8, dtype=np.float32)
        joint_state[:7] = env.joint_pos[:7]
        joint_state[7] = 0.04 if not env.grasped else 0.01

        frame_data = {
            "observation.images.image":  img_resized,
            "observation.images.image2": img_resized,
            "observation.state":         joint_state,
            "action":                    act.copy(),
            "task":                      "pick up the cube and lift it",
        }
        frames.append(frame_data)

        # Step environment
        flat_act = np.zeros(8, dtype=np.float32)
        flat_act[:7] = act[:7]
        flat_act[7] = act[6]

        obs_next, reward, terminated, truncated, info = env.step(flat_act)
        total_reward += float(reward[0])

    return frames, total_reward

def main():
    output_dir = "/checkpoint/physical-ai/franka_demos"
    if not os.path.exists(output_dir):
        output_dir = "/tmp/franka_demos"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating 25 expert demonstration episodes to {output_dir}...")
    all_episodes = []

    for ep_idx in range(25):
        seed = 100 + ep_idx
        ep_frames, ep_reward = generate_expert_episode(env_seed=seed, n_steps=100)
        chunked = util.chunk_episode_actions(ep_frames, chunk_size=50)

        # Store in CHW format for LeRobot / PyTorch model
        formatted_chunked = []
        for f in chunked:
            f_copy = dict(f)
            img1 = np.asarray(f["observation.images.image"])
            if img1.ndim == 3 and img1.shape[2] == 3:
                f_copy["observation.images.image"] = np.transpose(img1, (2, 0, 1))
            img2 = np.asarray(f["observation.images.image2"])
            if img2.ndim == 3 and img2.shape[2] == 3:
                f_copy["observation.images.image2"] = np.transpose(img2, (2, 0, 1))
            formatted_chunked.append(f_copy)

        ep_path = os.path.join(output_dir, f"demo_ep{ep_idx}_reward{ep_reward:.3f}.pkl")
        with open(ep_path, "wb") as f:
            pickle.dump(formatted_chunked, f)

        all_episodes.extend(formatted_chunked)
        print(f"  Episode {ep_idx:02d} (seed {seed}): {len(ep_frames)} frames, reward = {ep_reward:.3f}")

    combined_path = os.path.join(output_dir, "expert_dataset.pkl")
    with open(combined_path, "wb") as f:
        pickle.dump(all_episodes, f)

    print(f"Successfully generated {len(all_episodes)} demonstration samples across 25 episodes.")
    print(f"Saved to: {combined_path}")

if __name__ == "__main__":
    main()
