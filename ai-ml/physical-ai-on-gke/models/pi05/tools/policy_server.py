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
PI0.5 Policy Server via Ray Serve.

Loads the fine-tuned PI0.5 checkpoint produced by the fine-tuning notebook
(`02_vla_finetuning.ipynb`, written under `/mnt/cluster_storage/...`) and
serves it behind an HTTP endpoint so Isaac Lab sim workers, running on a
separate GPU, can query it over the network without ever loading the
3.4B-param model themselves.

A standard Ray Serve pattern: a `@serve.deployment` class wrapped in
`@serve.ingress(FastAPI())`, with `POST /predict` and `GET /stats`. The
HTTP body is pickled bytes (numpy arrays survive intact, no JSON dtype loss).

Initialization, per replica:
  1. Load `lerobot/pi05_libero_finetuned` from /mnt/local_storage (already
     staged on every node; if missing, snapshot_download fills it).
  2. Overlay the trained head weights with `strict=False` (the checkpoint
     only contains action_in_proj / action_out_proj / time_mlp_in / time_mlp_out).
  3. Build the same preprocessor used during training, using the dataset
     normalization `stats` saved into state.pkl.
  4. Patch `make_att_2d_masks` (same patch as training).

Request format (pickled dict over HTTP, raw: pre-batch, pre-normalization):
    {
        "observation.images.image":   (H, W, 3) uint8  OR  (3, H, W) float32,
        "observation.images.image2":  (H, W, 3) uint8  OR  (3, H, W) float32,
        "observation.state":          (8,) float32,
        "task":                       str,
    }

Response:
    {
        "action":      (n_action_steps, action_dim) np.float32,   # ready for sim to step through
        "action_dim":  int,
        "n_action_steps": int,
        "latency_ms":  float,
    }
"""
import io
import os
import pickle
import time
from pathlib import Path

import numpy as np
import torch
from fastapi import FastAPI, Request, Response
from ray import serve


# Public mirror of the PI0.5 model (see 02_vla_finetuning.ipynb). Staged per node,
# so no HF token or bucket credentials are needed at runtime.
MODEL_S3_URI = "s3://anyscale-public-materials-use2/ray_summit_robotics_2026/pi05_libero_finetuned"


# FastAPI app must live at module scope for Serve ingress to pick it up.
_app = FastAPI()


# ============================================================================
# Compat patches (same as training side)
# ============================================================================

def _apply_pi05_attention_mask_patch():
    """Tolerate pad/attention mask length mismatches. Same patch training uses."""
    import lerobot.policies.pi05.modeling_pi05 as mp
    if getattr(mp, "_PI05_MASK_PATCH_APPLIED", False):
        return
    _orig = mp.make_att_2d_masks

    def _patched(pad_masks, att_masks):
        pl, al = pad_masks.shape[-1], att_masks.shape[-1]
        if pl != al:
            L = min(pl, al)
            return _orig(pad_masks[..., :L], att_masks[..., :L])
        return _orig(pad_masks, att_masks)

    mp.make_att_2d_masks = _patched
    mp._PI05_MASK_PATCH_APPLIED = True


import pickle
import ray.cloudpickle


class _CPUUnpickler(pickle.Unpickler):
    """Allow loading a CUDA-tensor checkpoint on CPU or GPU host (defensive)."""
    def find_class(self, module, name):
        if module == "torch.storage" and name == "_load_from_bytes":
            return lambda b: torch.load(
                io.BytesIO(b),
                map_location="cuda" if torch.cuda.is_available() else "cpu",
                weights_only=False,
            )
        return super().find_class(module, name)


# ============================================================================
# Ray Serve deployment
# ============================================================================

@serve.deployment(
    ray_actor_options={"num_gpus": 0.5},
    max_ongoing_requests=8,
    health_check_timeout_s=300,
    health_check_period_s=120,
)
@serve.ingress(_app)
class PI05PolicyServer:
    """Serves the LIBERO-fine-tuned PI0.5 policy."""

    def __init__(
        self,
        checkpoint_path: str = "/checkpoint/physical-ai/checkpoint_round1/state.pkl",
        base_model_dir:  str = "/tmp/lerobot/pi05_libero_finetuned",
        device:          str = "cuda:0",
    ):
        self.checkpoint_path = Path(checkpoint_path)
        self.base_model_dir  = Path(base_model_dir)
        self.device          = device
        self._call_count     = 0
        self._total_latency  = 0.0
        self._load_model()

    def reconfigure(self, user_config: dict):
        """Allow Ray Serve to dynamically reconfigure deployment parameters."""
        if not user_config:
            return
        new_ckpt = user_config.get("checkpoint_path")
        if new_ckpt and Path(new_ckpt) != self.checkpoint_path:
            self.checkpoint_path = Path(new_ckpt)
            self._load_model()

    def _ensure_dependencies(self):
        """Ensure lerobot and patched transformers are available on this node."""
        try:
            import lerobot
            import transformers.models.siglip
        except ImportError:
            print("[PI05Server] Missing dependencies in container. Running /app/tools/setup_vla_deps.sh...", flush=True)
            import subprocess
            subprocess.run(["bash", "/app/tools/setup_vla_deps.sh"], check=True)
            print("[PI05Server] Dependencies installed successfully.", flush=True)

    def _stage_tokenizer(self):
        """Ensure PaliGemma tokenizer files are present in local HuggingFace cache."""
        dst = Path(os.path.expanduser("~/.cache/huggingface/hub"))
        tok_json = dst / "models--google--paligemma-3b-pt-224/snapshots/35e4f46485b4d07967e7e9935bc3786aad50687c/tokenizer.json"
        if tok_json.exists():
            return
        dst.mkdir(parents=True, exist_ok=True)
        mirror_path = Path(os.environ.get("MIRROR_ROOT", "/checkpoint/physical-ai/mirror")) / "paligemma_tokenizer" / "hub"
        if mirror_path.exists():
            import shutil
            shutil.copytree(str(mirror_path), str(dst), dirs_exist_ok=True)
            print(f"[PI05Server] Staged PaliGemma tokenizer from GCS mirror: {mirror_path} -> {dst}", flush=True)
            return
        try:
            import s3fs
            s3fs.S3FileSystem(anon=True).get(
                "anyscale-public-materials-use2/ray_summit_robotics_2026/paligemma_tokenizer/hub/",
                str(dst) + "/",
                recursive=True,
            )
            print("[PI05Server] Downloaded PaliGemma tokenizer from S3.", flush=True)
        except Exception as e:
            print(f"[PI05Server] Warning: failed to download tokenizer from S3: {e}", flush=True)

    def _ensure_base_model(self):
        """Make sure the PI0.5 base weights and tokenizer are on local disk on this node."""
        self._stage_tokenizer()
        if (self.base_model_dir / "config.json").exists():
            return
        self.base_model_dir.mkdir(parents=True, exist_ok=True)
        mirror_path = Path(os.environ.get("MIRROR_ROOT", "/checkpoint/physical-ai/mirror")) / "pi05_libero_finetuned"
        if (mirror_path / "config.json").exists():
            import shutil
            shutil.copytree(str(mirror_path), str(self.base_model_dir), dirs_exist_ok=True)
            return
        import fsspec
        fs, fs_path = fsspec.core.url_to_fs(MODEL_S3_URI)
        fs.get(fs_path, str(self.base_model_dir), recursive=True)

    def _load_model(self):
        print(f"[PI05Server] Loading checkpoint from {self.checkpoint_path}", flush=True)
        self._ensure_dependencies()
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"Checkpoint not found at {self.checkpoint_path}. "
                "Run the fine-tuning notebook (02) first."
            )

        with open(self.checkpoint_path, "rb") as f:
            try:
                state = _CPUUnpickler(f).load()
            except Exception:
                f.seek(0)
                state = ray.cloudpickle.load(f)

        trained_sd: dict = state["model"]
        self._dataset_stats: dict = state["stats"]
        self._train_step  = state.get("step", 0)
        self._train_epoch = state.get("epoch", 0)
        print(f"[PI05Server]   trained for {self._train_step} steps "
              f"across {self._train_epoch + 1} epoch(s)", flush=True)
        print(f"[PI05Server]   trainable keys in checkpoint: {len(trained_sd)}", flush=True)

        self._ensure_base_model()
        _apply_pi05_attention_mask_patch()

        from tools import util
        util.quiet_benign_lerobot_logs()

        from lerobot.policies.pi05 import PI05Policy
        from lerobot.policies.factory import make_pre_post_processors

        t0 = time.time()
        # NOTE: train_expert_only=True matches training. The action expert
        # heads we trained are the only thing we want to swap.
        #
        # strict=False for the BASE weights: model.safetensors omits
        # paligemma...embed_tokens.weight because PaliGemma ties it to
        # lm_head.weight (one tensor, stored once). Under the default
        # strict=True, lerobot's loader raises inside its own try/except and
        # prints "Warning: Could not remap state dict keys: Error(s) in loading
        # state_dict ..." after the weights are already in place -- noise that
        # reads like a load failure during every replica start.
        with util.quiet_benign_lerobot_prints():
            policy = PI05Policy.from_pretrained(
                str(self.base_model_dir),
                device=self.device,
                dtype=torch.float16,
                train_expert_only=True,
                strict=False,
            )
        # Overlay trained head weights. strict=False because the checkpoint
        # only contains action_in_proj / action_out_proj / time_mlp_in / time_mlp_out.
        missing, unexpected = policy.load_state_dict(trained_sd, strict=False)
        if unexpected:
            print(f"[PI05Server]   WARN unexpected keys in checkpoint: {unexpected[:5]}...", flush=True)
        policy.eval()
        self.policy = policy

        # Build the inference preprocessor + postprocessor the same way
        # training did, via `make_pre_post_processors` with the base model
        # dir as pretrained_path. The base model's preprocessor config
        # (normalization modes, feature keys) is what we trained against;
        # building "from scratch" would default to QUANTILES mode and break
        # because our checkpoint only stores mean/std stats.
        stats_t = {
            k: {sk: torch.as_tensor(sv, dtype=torch.float32) for sk, sv in v.items()}
            for k, v in self._dataset_stats.items()
        }
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy.config,
            pretrained_path=str(self.base_model_dir),
            dataset_stats=stats_t,
        )

        load_time = time.time() - t0
        self._load_time = load_time

        # Cache the policy's action dim from config (used in stats endpoint).
        from lerobot.utils.constants import ACTION
        self._action_dim = int(policy.config.output_features[ACTION].shape[0])
        self._n_action_steps = int(policy.config.n_action_steps)
        print(f"[PI05Server] Ready in {load_time:.1f}s. "
              f"action_dim={self._action_dim}, n_action_steps={self._n_action_steps}",
              flush=True)

    # -------------------------------------------------------------------- HTTP

    @_app.post("/predict")
    async def predict_http(self, request: Request):
        body = await request.body()
        obs_dict = pickle.loads(body)
        result = self.predict(obs_dict)
        return Response(content=pickle.dumps(result),
                        media_type="application/octet-stream")

    @_app.get("/stats")
    async def stats_http(self):
        return {
            "checkpoint":      str(self.checkpoint_path),
            "train_step":      self._train_step,
            "train_epoch":     self._train_epoch,
            "action_dim":      self._action_dim,
            "n_action_steps":  self._n_action_steps,
            "total_calls":     self._call_count,
            "avg_latency_ms":  self._total_latency / max(self._call_count, 1),
            "load_time_s":     self._load_time,
            "device":          self.device,
        }

    # -------------------------------------------------------------------- core

    def _build_batch(self, obs_dict: dict) -> dict:
        """Wrap the raw obs dict into the un-batched form the preprocessor expects.

        Inputs (from sim worker, all numpy):
            observation.images.image        (C, H, W) float32  OR  (H, W, C) uint8
            observation.images.image2       (C, H, W) float32  OR  (H, W, C) uint8
            observation.state               (8,) float32
            task                             str

        We accept HWC uint8 too for sim-worker convenience and transpose here.
        """
        batch: dict = {}

        for k, v in obs_dict.items():
            if k.startswith("observation.images."):
                arr = np.asarray(v)
                # Accept HWC uint8 from sim workers; convert to CHW float32.
                if arr.ndim == 3 and arr.shape[-1] == 3 and arr.dtype == np.uint8:
                    arr = np.transpose(arr, (2, 0, 1)).astype(np.float32)
                batch[k] = torch.as_tensor(arr, dtype=torch.float32, device=self.device)
            elif k == "observation.state":
                batch[k] = torch.as_tensor(np.asarray(v),
                                           dtype=torch.float32, device=self.device)
            elif k == "task":
                # Preprocessor's AddBatchDim wraps a plain str into [str]. Leave as-is.
                batch["task"] = v
            else:
                # Pass through unknown keys (defensive: preprocessor may want them).
                batch[k] = v

        return batch

    def predict(self, obs_dict: dict) -> dict:
        t0 = time.time()
        batch = self._build_batch(obs_dict)

        with torch.no_grad(), torch.autocast("cuda", torch.float16):
            batch = self.preprocessor(batch)
            # The preprocessor adds tokenized fields (input_ids, attention_mask,
            # etc.) on CPU. Training survives this because Ray Train's
            # prepare_model wraps the policy in DDP which auto-moves inputs;
            # at inference we have no DDP, so move everything to GPU here.
            batch = {
                k: (v.to(self.device) if torch.is_tensor(v) else v)
                for k, v in batch.items()
            }
            actions = self.policy.predict_action_chunk(batch)   # (B, n_steps, action_dim)

        # Postprocessor unnormalizes back to original action scale + moves to CPU.
        # predict_action_chunk returns a Tensor, which the postprocessor expects.
        actions_post = self.postprocessor(actions)
        actions_np = actions_post.detach().cpu().numpy() if torch.is_tensor(actions_post) else np.asarray(actions_post)

        # Strip the batch dim, the sim worker only sent one obs.
        if actions_np.ndim == 3:
            actions_np = actions_np[0]   # (n_steps, action_dim)

        latency_ms = (time.time() - t0) * 1000
        self._call_count += 1
        self._total_latency += latency_ms

        return {
            "action":         actions_np.astype(np.float32),
            "action_dim":     int(actions_np.shape[-1]),
            "n_action_steps": int(actions_np.shape[0]),
            "latency_ms":     latency_ms,
        }


def builder(args: dict = None):
    args = args or {}
    checkpoint_path = args.get(
        "checkpoint_path",
        "/checkpoint/physical-ai/checkpoint_round1/state.pkl"
    )
    base_model_dir = args.get(
        "base_model_dir",
        "/tmp/lerobot/pi05_libero_finetuned"
    )
    return PI05PolicyServer.bind(
        checkpoint_path=checkpoint_path,
        base_model_dir=base_model_dir,
    )

app = PI05PolicyServer.bind(
    checkpoint_path="/checkpoint/physical-ai/checkpoint_round1/state.pkl",
    base_model_dir="/tmp/lerobot/pi05_libero_finetuned",
)
