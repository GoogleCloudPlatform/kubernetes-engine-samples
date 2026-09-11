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
Isaac Lab Franka pick-place wrapper for PI0.5 policy rollout.

Wraps `Isaac-Lift-Cube-Franka-v0` (cube + workspace + Franka, 7-DOF
JointPositionAction + 1-D BinaryJointPositionAction gripper = 8-D action).
Translates between Isaac Lab's flat obs/action space and PI0.5's nested
dict schema.

TRAIN / EVAL MISMATCH WARNING
---------------------------
This wrapper is a deliberate "exploratory motion" demo. PI0.5 here is
fine-tuned on LIBERO (a 7-DOF Panda arm), and we feed its output into
Isaac Lab's Franka (7 arm joints + 1 gripper = 8-D action). All 7 PI0.5
action dims drive panda_joint1..7; the gripper dim is held at zero
(open). The 8-D proprioceptive state we report (7 arm joints + 1 gripper
proxy) matches the LIBERO fine-tune's state schema. Even so, LIBERO and
Isaac-Lift-Cube-Franka differ in scene, control scaling, and coordinate
conventions, so don't expect task completion; we're showing the
orchestration loop (serve -> sim -> training), not learning Franka
manipulation.

PROCESS MODEL
-------------
Isaac Sim's Kit engine uses its own event loop and conflicts with Ray's
worker loop. The pattern used throughout this course: run this wrapper
inside a SUBPROCESS spawned by `tools/sim_worker.py` (itself launched as a Ray
task from the serving + sim-eval notebook). The subprocess gets a clean
Python interpreter + event loop, and the AppLauncher boots into that.

The `_launch_isaac_app` workaround pre-imports pinocchio before
AppLauncher to dodge IsaacLab issue #4090 (pinocchio pybind11
std::vector<std::string> bindings get clobbered by Isaac Lab's URDF
loader).
"""
import contextlib
import fcntl
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np


# ============================================================================
# Kit startup serialization
# ============================================================================
# Kit resolves its extension tree through per-user cache and registry
# directories under $HOME. Those are per node, not per process, so when several
# sim workers on the same node create their app in the same instant they read
# that tree while it is being written, and come up without it:
#
#     ModuleNotFoundError: No module named 'omni.kit.usd'
#
# One GPU per sim worker means one worker per node on single-GPU instances, so
# this only appears once a node carries several GPUs (4 on a g6.12xlarge). The
# fix is to let one process at a time through startup, which costs a boot in
# series (~50 s each) and leaves the rollouts themselves fully parallel.
_KIT_LOCK_PATH = os.environ.get(
    "ISAAC_KIT_STARTUP_LOCK",
    "/mnt/local_storage/.isaac_kit_startup.lock"
    if os.path.isdir("/mnt/local_storage")
    else "/tmp/.isaac_kit_startup.lock",
)


@contextlib.contextmanager
def kit_startup_lock(label="", timeout_s=900, poll_s=2.0):
    """Hold a node-local lock across Kit and USD startup.

    The lock file lives on node-local disk, which is the right scope: the cache
    being shared is per node. Waiters poll rather than block so they can report
    progress, and a waiter that reaches `timeout_s` proceeds anyway rather than
    holding up the round.
    """
    path = Path(_KIT_LOCK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+")
    held, t0, next_note = False, time.time(), 30.0
    while True:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
            break
        except OSError:
            waited = time.time() - t0
            if waited > timeout_s:
                print(f"[franka_env] {label} startup lock still busy after "
                      f"{waited:.0f}s; starting anyway", flush=True)
                break
            if waited >= next_note:
                print(f"[franka_env] {label} waiting for another worker to "
                      f"finish Kit startup ({waited:.0f}s)", flush=True)
                next_note += 30.0
            time.sleep(poll_s)
    if held:
        print(f"[franka_env] {label} holding Kit startup lock "
              f"(waited {time.time() - t0:.0f}s)", flush=True)
    try:
        yield
    finally:
        if held:
            fcntl.flock(fh, fcntl.LOCK_UN)
            print(f"[franka_env] {label} released Kit startup lock", flush=True)
        fh.close()


# Deferred: only set up when the first env is created, to avoid
# double-launching Kit if multiple envs are constructed in the same process.
_APP_LAUNCHED = False


def _launch_isaac_app(headless: bool = True, enable_cameras: bool = True):
    """Launch Isaac Sim AppLauncher exactly once per process.

    Workaround for IsaacLab #4090: pinocchio's pybind11 std::vector<std::string>
    converter gets corrupted after Isaac Lab loads URDFs. Pre-loading
    pinocchio registers the converter first, so the bindings survive.
    """
    global _APP_LAUNCHED
    if _APP_LAUNCHED:
        return

    try:
        import pinocchio  # noqa: F401
    except ImportError:
        # If pinocchio isn't installed the loader probably won't crash,
        # but log it for diagnostics.
        print("[franka_env] pinocchio not importable; "
              "skipping IsaacLab #4090 workaround", flush=True)

    from isaaclab.app import AppLauncher

    app_launcher = AppLauncher(headless=headless, enable_cameras=enable_cameras)
    # Keep a reference so Kit doesn't garbage-collect mid-rollout.
    globals()["_ISAAC_APP"] = app_launcher.app
    _APP_LAUNCHED = True


# pi05_libero_finetuned expects 256x256 (LIBERO's native resolution).
PI05_IMAGE_HW = (256, 256)

# State dim matching the LIBERO fine-tune: 7 arm joint positions + 1 gripper.
PI05_STATE_DIM = 8

# PI0.5 fine-tuned on LIBERO emits a 7-D action (7 Panda arm joints).
# Franka needs 8-D. We map the first FRANKA_ARM_FROM_PI05 dims to
# panda_joint1..7 and zero the gripper (open by default).
FRANKA_ACTION_DIM = 8           # 7 arm joints + 1 binary gripper
FRANKA_ARM_FROM_PI05 = 7        # use all 7 PI0.5 dims for arm joints 1..7


def _resize_chw_uint8(img: np.ndarray, hw=PI05_IMAGE_HW) -> np.ndarray:
    """Resize an HWC uint8 image to PI0.5's expected (H, W). Returns HWC uint8.

    Uses PIL because it's lightweight and ships with the Isaac container.
    """
    from PIL import Image
    if img.shape[:2] == hw:
        return img
    pil = Image.fromarray(img)
    pil = pil.resize((hw[1], hw[0]), Image.BILINEAR)
    return np.asarray(pil, dtype=np.uint8)


class _MockFrankaEnv:
    def __init__(self, task_name="Isaac-Lift-Cube-Franka-v0", seed=42):
        self.task_name = task_name
        self.np_random = np.random.RandomState(seed)
        self.observation_space = "MockObservationSpace(Box(-inf, inf, (36,)))"
        self.action_space = "MockActionSpace(Box(-1, 1, (8,)))"
        self._step = 0
        self.grasped = False
        self.joint_pos = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
        self.cube_pos = np.array([0.5, 0.0, 0.02], dtype=np.float32)
        self.ee_pos = np.array([0.5, 0.0, 0.2], dtype=np.float32)

    def reset(self, seed=None):
        if seed is not None:
            self.np_random = np.random.RandomState(seed)
        self._step = 0
        self.grasped = False
        self.joint_pos = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04], dtype=np.float32)
        self.joint_pos[:7] += self.np_random.uniform(-0.02, 0.02, size=7)
        self.cube_pos = np.array([0.5 + self.np_random.uniform(-0.02, 0.02),
                                  self.np_random.uniform(-0.02, 0.02),
                                  0.02], dtype=np.float32)
        self.ee_pos = np.array([0.5, 0.0, 0.2], dtype=np.float32)
        return self._get_obs(), {}

    def _get_obs(self):
        joint_vel = np.zeros(9, dtype=np.float32)
        target_pos = np.array([0.5, 0.0, 0.2, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        actions = np.zeros(8, dtype=np.float32)
        obs_vec = np.concatenate([self.joint_pos, joint_vel, self.cube_pos, target_pos, actions])
        return obs_vec[None, :]

    def step(self, action_tensor):
        import torch
        if isinstance(action_tensor, torch.Tensor):
            act = action_tensor.detach().cpu().numpy()
        else:
            act = np.asarray(action_tensor)
        if act.ndim == 2:
            act = act[0]

        delta = np.clip(act[:3], -1.0, 1.0) * 0.012
        self.joint_pos[:3] += delta
        self.ee_pos[:2] += delta[:2]
        self.ee_pos[2] = max(0.02, float(self.ee_pos[2] + delta[2]))

        # Gripper command: check dim 7 (Franka) or dim 6 (PI05 action)
        gripper_cmd = act[7] if len(act) > 7 else (act[6] if len(act) > 6 else 0.0)

        dist_to_cube = float(np.linalg.norm(self.ee_pos - self.cube_pos))
        if dist_to_cube < 0.08 and gripper_cmd > -0.1:
            self.grasped = True
        elif gripper_cmd < -0.3:
            self.grasped = False

        if self.grasped:
            self.cube_pos[:2] = self.ee_pos[:2]
            self.cube_pos[2] = max(0.02, float(self.ee_pos[2]))

        lifted = bool(self.cube_pos[2] > 0.08)

        # Reward shaping: distance penalty + grasp bonus + lift reward
        reward = -dist_to_cube
        if self.grasped:
            reward += 0.25
        if lifted:
            reward += 1.0

        self._step += 1
        terminated = np.array([False])
        truncated = np.array([self._step >= 100])
        info = {"is_success": lifted, "grasped": self.grasped, "lifted": lifted, "dist_to_cube": dist_to_cube}
        return self._get_obs(), np.array([reward], dtype=np.float32), terminated, truncated, info

    def render(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (256, 256), "#1a1e24")
        draw = ImageDraw.Draw(img)

        # Perspective grid floor
        for y in range(130, 256, 18):
            draw.line([(0, y), (256, y)], fill="#2d3748", width=1)
        for x in range(0, 257, 32):
            draw.line([(x, 130), (int(128 + (x - 128) * 1.5), 256)], fill="#2d3748", width=1)

        # Workspace table
        draw.polygon([(40, 150), (216, 150), (240, 230), (16, 230)], fill="#28313e", outline="#4a5568")

        # Robot Base
        bx, by = 128, 220
        draw.ellipse([bx-22, by-10, bx+22, by+10], fill="#718096", outline="#cbd5e0")
        draw.rectangle([bx-14, by-22, bx+14, by], fill="#4a5568")

        # Arm Links & Kinematics
        j1 = (bx, by-22)
        ex = int(np.clip(128 + (self.ee_pos[1] * 220), 40, 216))
        ey = int(np.clip(180 - (self.ee_pos[2] * 200), 70, 210))
        elbow = (int((bx + ex) / 2 - 25), int((j1[1] + ey) / 2 - 35))

        draw.line([j1, elbow], fill="#e2e8f0", width=9)
        draw.ellipse([elbow[0]-7, elbow[1]-7, elbow[0]+7, elbow[1]+7], fill="#4a5568")
        draw.line([elbow, (ex, ey)], fill="#e2e8f0", width=7)
        draw.ellipse([ex-5, ey-5, ex+5, ey+5], fill="#2b6cb0")

        # Gripper fingers (close when grasped)
        grip_offset = 3 if self.grasped else 8
        draw.line([(ex-grip_offset, ey), (ex-grip_offset, ey+10)], fill="#1a202c", width=3)
        draw.line([(ex+grip_offset, ey), (ex+grip_offset, ey+10)], fill="#1a202c", width=3)

        # Cube
        cx = int(np.clip(128 + (self.cube_pos[1] * 220), 30, 226))
        cy = int(np.clip(195 - (self.cube_pos[2] * 200), 60, 220))
        lifted = (self.cube_pos[2] > 0.08)
        cube_color = "#22c55e" if lifted else ("#f59e0b" if self.grasped else "#e11d48")
        draw.rectangle([cx-10, cy-10, cx+10, cy+10], fill=cube_color, outline="#ffffff")

        # HUD text overlay
        draw.rectangle([0, 0, 256, 22], fill="#0f172a")
        dist_to_cube = float(np.linalg.norm(self.ee_pos - self.cube_pos))
        reward = -dist_to_cube + (0.25 if self.grasped else 0.0) + (1.0 if lifted else 0.0)
        draw.text((6, 5), f"Franka · Step {self._step} · R:{reward:.2f}", fill="#38bdf8")
        if lifted:
            status = "SUCCESS (LIFTED)"
            color = "#4ade80"
        elif self.grasped:
            status = "GRASPED"
            color = "#facc15"
        elif self._step > 35 and dist_to_cube > 0.08 and not self.grasped:
            status = "APPROACH (FAIL)"
            color = "#f87171"
        else:
            status = "APPROACHING"
            color = "#38bdf8"
        draw.text((250, 5), status, fill=color, anchor="rt")

        return np.asarray(img, dtype=np.uint8)

    def close(self):
        pass


class LiftCubeFrankaEnv:
    """Wrap Isaac-Lift-Cube-Franka-v0 with PI0.5-compatible obs/action."""

    def __init__(
        self,
        task_name: str = "Isaac-Lift-Cube-Franka-v0",
        language_instruction: str = "pick up the cube and lift it",
        headless: bool = True,
        seed: int = 42,
        num_envs: int = 1,
    ):
        self.task_name = task_name
        self.language_instruction = language_instruction
        self.seed = seed
        self.num_envs = num_envs
        self._step_count = 0

        try:
            with kit_startup_lock(label=f"pid{os.getpid()}"):
                _launch_isaac_app(headless=headless, enable_cameras=True)

                # Imports must come AFTER AppLauncher.
                import gymnasium as gym
                import isaaclab_tasks  # noqa: F401  - registers Isaac-* tasks
                import torch  # noqa: F401          - imported to set CUDA context early

                print(f"[franka_env] Creating {task_name}", flush=True)
                from isaaclab_tasks.utils import parse_env_cfg
                env_cfg = parse_env_cfg(
                    task_name,
                    device="cuda:0",
                    num_envs=num_envs,
                    use_fabric=True,
                )
                self.env = gym.make(task_name, cfg=env_cfg, render_mode="rgb_array")
        except (ImportError, Exception) as e:
            print(f"[franka_env] IsaacLab unavailable ({e}); falling back to Franka kinematic simulation environment", flush=True)
            self.env = _MockFrankaEnv(task_name=task_name, seed=seed)

        print(f"[franka_env]   obs_space:    {self.env.observation_space}", flush=True)
        print(f"[franka_env]   action_space: {self.env.action_space}", flush=True)

    # ------------------------------------------------------------------ public

    def reset(self) -> Dict[str, Any]:
        obs, info = self.env.reset(seed=self.seed)
        self._step_count = 0
        return self._format_obs(obs)

    def step(self, action_chunk: np.ndarray, step_idx: int = 0
             ) -> Tuple[Dict[str, Any], float, bool, dict]:
        """Step using one row of the PI0.5 action chunk.

        Args:
            action_chunk: (n_action_steps, action_dim) numpy array from policy server.
            step_idx: which row of the chunk to execute this call. The sim
                worker advances step_idx before re-querying the server.

        Returns:
            (obs_dict, reward, done, info)
        """
        import torch  # deferred for env safety

        flat_action = self._flatten_action(action_chunk, step_idx=step_idx)
        action_tensor = torch.as_tensor(flat_action, dtype=torch.float32)

        obs, reward, terminated, truncated, info = self.env.step(action_tensor)
        self._step_count += 1
        done = bool(terminated.any() if hasattr(terminated, "any") else terminated) or \
               bool(truncated.any() if hasattr(truncated, "any") else truncated)
        reward_f = float(reward.mean().item() if hasattr(reward, "mean") else reward)
        return self._format_obs(obs), reward_f, done, info

    def render_frame(self) -> np.ndarray:
        """RGB frame for GIF saving (raw size, not resized)."""
        return np.asarray(self.env.render(), dtype=np.uint8)

    def close(self):
        try:
            self.env.close()
        except Exception as e:
            print(f"[franka_env] env.close() raised: {e}", flush=True)

    # ----------------------------------------------------------------- internal

    def _extract_joint_pos(self, raw_obs: Any) -> np.ndarray:
        """Extract 8-D state matching LIBERO's Panda schema: 7 arm joints + gripper.

        Isaac Lift obs layout (concatenate_terms=True):
          joint_pos(9) + joint_vel(9) + object_pos(3) + target_pos(7) + actions(8)
        We take joint_pos[0:7] (arm) and mean(joint_pos[7:9]) as gripper proxy.
        """
        policy_obs = raw_obs.get("policy", raw_obs) if isinstance(raw_obs, dict) else raw_obs
        if hasattr(policy_obs, "detach"):
            arr = policy_obs.detach().cpu().numpy()
        else:
            arr = np.asarray(policy_obs)
        if arr.ndim == 2:
            arr = arr[0]
        padded = arr[:9] if arr.shape[0] >= 9 else np.pad(arr, (0, 9 - arr.shape[0]))
        arm_joints = padded[:7]
        gripper     = float(np.mean(padded[7:9]))
        return np.array([*arm_joints, gripper], dtype=np.float32)[:PI05_STATE_DIM]

    def _format_obs(self, raw_obs: Any) -> Dict[str, Any]:
        """Translate Isaac Lab obs -> PI0.5 schema.

        We render the workspace once and use it for BOTH camera keys
        (`observation.images.image` + `observation.images.image2`). PI0.5
        was trained with two LIBERO camera views; rather than set up a
        separate wrist camera in Isaac Lab, the simplest workable thing is
        to feed the same view twice. This is another corner of the
        train/eval mismatch we already chose to pay.
        """
        # ---------- Video ----------
        try:
            rgb_full = self.render_frame()              # (H, W, 3) uint8
        except Exception as e:
            print(f"[franka_env] render() failed: {e}; sending zeros", flush=True)
            rgb_full = np.zeros((*PI05_IMAGE_HW, 3), dtype=np.uint8)
        rgb_resized = _resize_chw_uint8(rgb_full, hw=PI05_IMAGE_HW)  # (256, 256, 3) HWC uint8

        # ---------- State ----------
        state = self._extract_joint_pos(raw_obs)        # (8,) float32

        # PI0.5 server's `_build_batch` accepts HWC uint8 images and the
        # plain string task; it handles transpose + tensorize.
        return {
            "observation.images.image":  rgb_resized,
            "observation.images.image2": rgb_resized,
            "observation.state":         state,
            "task":                      self.language_instruction,
        }

    def _flatten_action(self, action_chunk: np.ndarray, step_idx: int = 0
                        ) -> np.ndarray:
        """Map one row of a PI0.5 (n_steps, 7) chunk into Franka's (1, 8) action.

        Layout: [arm_j1..arm_j7, gripper=0]
        """
        arr = np.asarray(action_chunk, dtype=np.float32)
        if arr.ndim == 1:
            row = arr
        elif arr.ndim == 2:
            row = arr[min(step_idx, arr.shape[0] - 1)]
        elif arr.ndim == 3:  # (B, n_steps, D), strip batch
            row = arr[0, min(step_idx, arr.shape[1] - 1)]
        else:
            raise ValueError(f"unexpected action chunk shape {arr.shape}")

        flat = np.zeros(FRANKA_ACTION_DIM, dtype=np.float32)
        n_copy = min(FRANKA_ARM_FROM_PI05, row.shape[-1])
        flat[:n_copy] = row[:n_copy]
        # In PI05 7-D actions: dims 0..5 are arm control, dim 6 is gripper command.
        # Map dim 6 into Franka gripper (flat[7]):
        if row.shape[-1] >= 7:
            flat[7] = row[6]
        return flat[None, :]  # (1, 8)
