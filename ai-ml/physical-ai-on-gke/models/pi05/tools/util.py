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
Training utilities for the VLA fine-tuning + closed-loop notebooks.

Helpers shared across the phase scripts (02 fine-tuning, 03 serving +
sim eval). They live here so the notebooks stay focused on the Ray-specific
orchestration, while this module owns the model plumbing.

Sections:
  * PI0.5 attention-mask patch
  * load_pi05_policy
  * NumpyToTorchCollate
  * train_step / optimizer_step
  * truncate_batch
  * build_lr_scheduler
  * make_checkpoint / load_checkpoint  (preserves dataset stats for serving)
  * stage_model_to_local / stage_on_all_nodes (model only -- datasets stream)
"""

import contextlib
import logging
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
from ray.data.iterator import NumpyBatchCollateFn


# ============================================================================
# Benign-log suppression
# ============================================================================
# lerobot's PI0.5 loader logs two warnings on every load that look like failures
# and are not. Both are artifacts of how it re-implements from_pretrained:
#
#   "Vision embedding key might need handling: ...patch_embedding.weight/.bias"
#       _fix_pytorch_state_dict_keys warns on any key containing
#       "patch_embedding" in case a checkpoint needs remapping. Ours does not --
#       both keys are present in model.safetensors under the names the model
#       expects, and they load normally.
#
#   "Missing keys when loading state dict: 1 keys
#      - ...paligemma.model.language_model.embed_tokens.weight"
#       PaliGemma's text config sets tie_word_embeddings=True, so embed_tokens
#       and lm_head are the SAME tensor and safetensors stores it once, as
#       lm_head.weight. Loading lm_head fills the embedding table through the
#       shared storage; the key is absent by design, not lost.
#
# Filtered at the root logger (lerobot calls the module-level logging.warning,
# so records go to root) and only for these exact prefixes -- every other
# warning still comes through.
# The tied-embedding report is print()ed rather than logged, so it needs the
# stdout filter below -- EXCEPT inside a Ray Train worker, where Ray Train v2
# patches builtins.print to forward through the root logger instead
# (ray/train/v2/_internal/logging/patch_print.py), which is why these two lines
# are listed for both filters. Matched exactly, not by prefix: the header
# carries its "1 keys" count and the bullet its full key name, so a load missing
# anything ELSE still reports in full instead of being silently swallowed.
_TIED_EMBED_KEY = (
    "model.paligemma_with_expert.paligemma.model.language_model.embed_tokens.weight"
)
_BENIGN_LEROBOT_PRINTS = (
    "Missing keys when loading state dict: 1 keys",
    f"  - {_TIED_EMBED_KEY}",
)

_BENIGN_LEROBOT_LOG_PREFIXES = (
    "Vision embedding key might need handling:",
    *_BENIGN_LEROBOT_PRINTS,
)


class _BenignLerobotFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith(_BENIGN_LEROBOT_LOG_PREFIXES)


def quiet_benign_lerobot_logs():
    """Drop lerobot's known-benign PI0.5 load warnings. Idempotent."""
    root = logging.getLogger()
    for target in (root, *root.handlers):
        if not any(isinstance(f, _BenignLerobotFilter) for f in target.filters):
            target.addFilter(_BenignLerobotFilter())


class _LineFilterWriter:
    """Line-buffered stdout proxy that drops an exact set of lines."""

    def __init__(self, stream, drop):
        self._stream = stream
        self._drop = drop
        self._buf = ""

    def write(self, s):
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line not in self._drop:
                self._stream.write(line + "\n")
        return len(s)

    def flush(self):
        if self._buf:
            if self._buf not in self._drop:
                self._stream.write(self._buf)
            self._buf = ""
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


@contextlib.contextmanager
def quiet_benign_lerobot_prints():
    """Suppress lerobot's tied-embedding "Missing keys" report on stdout.

    Scoped to the from_pretrained call. Anything lerobot prints that is not one
    of the two exact benign lines passes straight through, including tracebacks.
    """
    original = sys.stdout
    proxy = _LineFilterWriter(original, _BENIGN_LEROBOT_PRINTS)
    sys.stdout = proxy
    try:
        yield
    finally:
        proxy.flush()
        sys.stdout = original


# ============================================================================
# PI0.5 attention-mask patch
# ============================================================================
def apply_pi05_attention_mask_patch():
    """Tolerate pad/attention mask length mismatches in PI0.5's preprocessor.

    lerobot's preprocessor can produce pad_masks and att_masks of slightly
    different sequence lengths (typically off-by-one after image tokenization);
    upstream make_att_2d_masks doesn't handle that and crashes. We truncate
    both masks to the shorter length on mismatch. Idempotent.
    """
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


# ============================================================================
# Model loading
# ============================================================================
def load_pi05_policy(pretrained_path):
    """Load PI0.5 in fp16, freeze backbone, train only 4 projection heads.

    train_expert_only=True configures the model's expert branch as trainable
    but doesn't actually call requires_grad_(True) on those params -- we do
    that manually here for the 4 action-head modules.
    """
    apply_pi05_attention_mask_patch()
    quiet_benign_lerobot_logs()
    from lerobot.policies.pi05 import PI05Policy

    # strict=False: the base checkpoint legitimately omits
    # paligemma...embed_tokens.weight, which is tied to lm_head.weight (see
    # quiet_benign_lerobot_logs). Left at the default strict=True, lerobot's
    # loader raises inside its own try/except and prints
    #   "Warning: Could not remap state dict keys: Error(s) in loading
    #    state_dict for PI05Policy: Missing key(s) ..."
    # -- alarming, but the weights are already copied by then, so it changes
    # nothing except the log. Say what we mean instead.
    with quiet_benign_lerobot_prints():
        policy = PI05Policy.from_pretrained(
            str(pretrained_path), device="cuda", dtype=torch.float16,
            train_expert_only=True, strict=False,
        )
    for p in policy.parameters():
        p.requires_grad = False
    for name, module in policy.model.named_children():
        if name in {"action_in_proj", "action_out_proj", "time_mlp_in", "time_mlp_out"}:
            for p in module.parameters():
                p.requires_grad = True
    return policy


# ============================================================================
# Collation: numpy dicts -> GPU tensors
# ============================================================================
class NumpyToTorchCollate(NumpyBatchCollateFn):
    """Convert a numpy batch dict into tensors on the target device.

    Ray Data delivers batches as numpy arrays. This moves them to GPU as
    torch tensors, preserving dtype semantics: integer -> torch.long, bool
    -> torch.bool, everything else -> torch.float32. The ``task`` column
    stays as a Python list of strings (language conditioning).

    ``image_keys`` names the camera columns, which stay **uint8** all the way
    through Ray Data and are widened to float32 only here, on the GPU. That
    matters on small nodes: a 256x256x3 frame is 197 KB as uint8 and 786 KB as
    float32, so casting inside the Ray Data pipeline would quadruple every
    block held in the object store -- while the datasource's block sizing
    (``estimated_row_size_bytes``) still assumes uint8, so the streaming
    executor would under-count its own memory use by 4x and the host OOM
    killer would take out the raylet. Cast late, on device, instead.

    Without this list the base-class rule would send uint8 images to
    torch.long (integer -> long), which is 8 bytes per channel value -- worse
    than the float32 it replaced. Camera columns must be named explicitly.
    """

    def __init__(self, device, image_keys=()):
        self.device = device
        self.image_keys = set(image_keys)

    def __call__(self, batch):
        task = list(batch.pop("task"))
        result = {}
        for k, v in batch.items():
            arr = np.asarray(v)
            if arr.dtype == object:
                arr = np.stack([np.asarray(x) for x in v])
            if k in self.image_keys:
                # uint8 -> GPU -> float32, same values as the old CPU-side
                # .astype(np.float32) (no /255 rescale; the normalizer step
                # in the preprocessor owns scaling).
                #
                # Arrow hands back read-only buffers, and torch.from_numpy on one
                # warns "The given NumPy array is not writable ... undefined
                # behavior". Nothing here writes through the tensor -- .to() copies
                # to the GPU immediately -- but copy the rare read-only batch
                # rather than leave a warning that invites the reader to wonder.
                if not arr.flags.writeable:
                    arr = arr.copy()
                result[k] = torch.from_numpy(arr).to(self.device).float()
            elif np.issubdtype(arr.dtype, np.integer):
                result[k] = torch.tensor(arr, dtype=torch.long, device=self.device)
            elif np.issubdtype(arr.dtype, np.bool_):
                result[k] = torch.tensor(arr, dtype=torch.bool, device=self.device)
            else:
                result[k] = torch.tensor(arr, dtype=torch.float32, device=self.device)
        result["task"] = task
        return result


# ============================================================================
# Preprocessor construction
# ============================================================================
def build_preprocessor(policy_config, base_dir, dataset_stats, device="cuda"):
    """Build PI0.5's preprocessor pipeline, pinned to `device`.

    The pipeline's last step is a DeviceProcessorStep, and when the pipeline is
    loaded via `pretrained_path` that step's device comes from the saved
    preprocessor JSON in `pi05_base` -- which says "cpu". It does NOT inherit
    policy_config.device. Left alone it drags every batch back off the GPU, so
    the CUDA model then meets CPU token ids:

        RuntimeError: Expected all tensors to be on the same device, but found
        at least two devices, cuda:0 and cpu! (index_select)

    tools/policy_server.py works around this by re-uploading the batch after
    preprocessing; overriding the step is cheaper -- it avoids a pointless
    GPU -> CPU -> GPU round trip of both camera streams per step.
    """
    from lerobot.policies.factory import make_pre_post_processors

    preprocessor, postprocessor = make_pre_post_processors(
        policy_config,
        pretrained_path=str(base_dir),
        dataset_stats=dataset_stats,
        preprocessor_overrides={"device_processor": {"device": str(device)}},
    )
    return preprocessor, postprocessor


# ============================================================================
# Sequence truncation
# ============================================================================
def truncate_batch(batch, max_len):
    """Clip 2D+ sequence/mask tensors to max_len tokens. max_len=0 disables."""
    if not max_len:
        return batch
    for k in ("tokens", "input_ids", "masks", "attention_mask",
              "pad_masks", "att_masks", "img_masks", "image_masks"):
        if k in batch and hasattr(batch[k], "ndim") and batch[k].ndim >= 2:
            batch[k] = batch[k][..., :max_len]
    return batch


# ============================================================================
# Training step helpers: vanilla PyTorch wrapped in autocast
# ============================================================================
def train_step(policy, batch, preprocessor, max_len, grad_accum, scaler):
    """One forward + scaled backward. Returns scalar loss value."""
    batch = preprocessor(batch)
    batch = truncate_batch(batch, max_len)
    batch.pop("task", None)
    batch.pop("task_index", None)
    # Emitted alongside chunked actions to mark padded timesteps. PI0.5's forward
    # does not accept it (nothing in lerobot's pi05 or its processors reads
    # action_is_pad), so drop it here. Kept in the dataset because masking the
    # loss over padded timesteps is the natural next refinement.
    batch.pop("action_is_pad", None)
    with torch.autocast("cuda", torch.float16):
        out = policy(batch)
        loss = out.loss if hasattr(out, "loss") else out[0]
    scaler.scale(loss / grad_accum).backward()
    return float(loss.detach())


def optimizer_step(policy, optimizer, scaler, scheduler):
    """Unscale, clip grads, step optimizer + LR schedule."""
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(
        [p for p in policy.parameters() if p.requires_grad], max_norm=1.0,
    )
    scaler.step(optimizer)
    scaler.update()
    optimizer.zero_grad(set_to_none=True)
    scheduler.step()


# ============================================================================
# LR schedule
# ============================================================================
def build_lr_scheduler(optimizer, config, num_workers, last_step):
    """Linear warmup -> cosine decay LR schedule.

    The schedule spans the updates the run will ACTUALLY perform. Sizing it from
    ``total_rows`` alone, as this did, silently breaks any run that stops at
    ``max_train_steps``: a 50-batch smoke run at grad_accum=16 makes 3 optimizer
    updates, while a schedule built for a full 273k-row epoch spends its first
    854 updates warming up. Those 3 updates then land at ~1e-7 instead of the
    configured 5e-5, the weights move by ~1e-6 relative -- fp16 noise -- and the
    "retrained" policy behaves identically to the one it started from.
    """
    import math
    bs = int(config.get("batch_size", 1))
    ga = int(config.get("grad_accum", 1))
    nepochs = int(config.get("num_epochs", 1))
    rows = int(config.get("total_rows", 10000))
    warm_fr = float(config.get("warmup_frac", 0.1))
    max_train_steps = config.get("max_train_steps")

    rows_per_worker = rows // num_workers
    if max_train_steps:
        # max_train_steps counts batches, and one update covers grad_accum of
        # them. Never fewer than 1 update, or the schedule divides by zero.
        total_steps = max(int(max_train_steps) // ga, 1)
    else:
        total_steps = max(rows_per_worker // (bs * ga), 1) * nepochs
    warmup_steps = int(total_steps * warm_fr)

    # last_step is a batch count (what the train loop tracks); the scheduler
    # counts updates.
    last_step = int(last_step) // ga

    def lr_lambda(s):
        if s < warmup_steps:
            return s / max(warmup_steps, 1)
        progress = (s - warmup_steps) / max(total_steps - warmup_steps, 1)
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    return torch.optim.lr_scheduler.LambdaLR(
        optimizer, lr_lambda, last_epoch=last_step - 1 if last_step > 0 else -1,
    )


# ============================================================================
# Action chunking for sim-recorded frames
# ============================================================================
def chunk_episode_actions(frames, chunk_size):
    """Give each frame of ONE episode an ``(chunk_size, action_dim)`` action chunk.

    LIBERO rows get their chunks inside the datasource
    (``LeRobotReadTask._chunk_action_column``), but sim workers record a single
    executed action per frame. Both sides must agree, or ``Dataset.union()`` in
    the closed loop sees two different shapes for ``action`` and training breaks
    on whichever batch comes from the other source.

    Pass the frames of a single episode, in order -- one trajectory pickle is one
    episode. Padding repeats the last real action and is flagged in
    ``action_is_pad``, matching the datasource's convention.
    """
    if chunk_size <= 1 or not frames:
        return frames

    actions = np.stack([np.asarray(f["action"], dtype=np.float32) for f in frames])
    if actions.ndim != 2:
        raise ValueError(
            f"expected one action per frame, got array of shape {actions.shape}; "
            f"are these frames already chunked?"
        )
    n_frames = len(frames)
    last = n_frames - 1
    wanted = np.arange(n_frames)[:, None] + np.arange(chunk_size)[None, :]
    chunks = actions[np.minimum(wanted, last)]
    is_pad = wanted > last

    out = []
    for i, frame in enumerate(frames):
        chunked = dict(frame)
        chunked["action"] = chunks[i]
        chunked["action_is_pad"] = is_pad[i]
        out.append(chunked)
    return out


# ============================================================================
# Resume sanity check
# ============================================================================
def resume_would_skip_training(start_epoch, num_epochs):
    """True when a restored checkpoint leaves the epoch loop with nothing to do.

    `load_checkpoint` returns `state["epoch"] + 1`, so re-running a completed
    single-epoch job gives `for epoch in range(1, 1)` -- zero iterations. The
    loop body never executes, `metrics` is never assigned, no `ray.train.report`
    happens, and `TorchTrainer.fit()` hands back the PREVIOUS run's checkpoint
    and metrics. The caller then prints a plausible loss and a valid
    checkpoint path for training that did not occur.

    Resuming a finished run is legitimate; silently presenting it as a fresh
    result is not. Callers use this to say so out loud.

    To actually retrain, either raise `num_epochs`, or give `RunConfig` a new
    `name` so Ray Train starts a fresh run instead of restoring this one.
    """
    return start_epoch >= num_epochs


# ============================================================================
# Checkpoint I/O
# ============================================================================
def make_checkpoint(policy, optimizer, scaler, epoch, step, stats,
                    base_model_repo, camera_rename):
    """Pickle trainable-only state + dataset stats into a Ray Train Checkpoint.

    Stats are included so tools/policy_server.py can rebuild the same preprocessor
    at inference time without re-reading the dataset. base_model_repo and
    camera_rename are saved as breadcrumbs for downstream consumers.
    """
    import ray.cloudpickle as pickle
    import ray.train

    trainable_keys = {k for k, p in policy.module.named_parameters() if p.requires_grad}
    full_sd = policy.module.state_dict()
    trainable_sd = {k: v for k, v in full_sd.items() if k in trainable_keys}

    ckpt_dir = tempfile.mkdtemp(prefix="pi05_ckpt_")
    with open(os.path.join(ckpt_dir, "state.pkl"), "wb") as f:
        pickle.dump(
            {"model":            trainable_sd,
             "optim":            optimizer.state_dict(),
             "scaler":           scaler.state_dict(),
             "epoch":            epoch,
             "step":             step,
             "stats":            stats,
             "base_model_repo":  base_model_repo,
             "camera_rename":    camera_rename},
            f,
        )
    return ray.train.Checkpoint.from_directory(ckpt_dir)


def load_checkpoint(checkpoint, policy, optimizer, scaler):
    """Restore from a Ray Train checkpoint. Returns (start_epoch, start_step)."""
    import ray.cloudpickle as pickle
    with checkpoint.as_directory() as d:
        with open(os.path.join(d, "state.pkl"), "rb") as f:
            state = pickle.load(f)
    policy.module.load_state_dict(state["model"], strict=False)
    optimizer.load_state_dict(state["optim"])
    if "scaler" in state:
        scaler.load_state_dict(state["scaler"])
    return state["epoch"] + 1, state.get("step", 0)


# ============================================================================
# Phase transitions: host-RAM headroom gating
# ============================================================================
def node_host_memory(ray_module):
    """Report (hostname, MemTotal, MemAvailable, Shmem) in MiB for each GPU node."""
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    @ray_module.remote(num_cpus=0)
    def _mem():
        import socket
        d = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            d[k] = int(v.strip().split()[0]) // 1024
        return {"host": socket.gethostname(), "total": d["MemTotal"],
                "available": d["MemAvailable"], "shmem": d.get("Shmem", 0)}

    nodes = [n for n in ray_module.nodes()
             if n.get("Alive") and n.get("Resources", {}).get("GPU")]
    return ray_module.get([
        _mem.options(scheduling_strategy=NodeAffinitySchedulingStrategy(
            node_id=n["NodeID"], soft=False)).remote()
        for n in nodes
    ])


def wait_for_host_headroom(ray_module, need_mib=17_000, timeout_s=240,
                           poll_s=10, log_fn=print, require_all=False,
                           per_gpu=True, num_workers=None):
    """Give each GPU node a moment to free host RAM before a phase loads PI0.5.

    Loading PI0.5 costs a transient ~16 GB of host RAM per worker even though
    the loaded policy stays ~3.3 GB resident, because the safetensors state
    dict is materialized on the host before the weights move to the GPU. A node
    that has just finished a Ray Train round is still holding plasma and idle
    spill workers, so this waits for it to settle and reports what it is
    waiting on.

    Flexible about cluster shape, which is the point:

    * `require_all=False` (default) waits for ANY node to qualify, which is
      right for a single Ray Serve replica since it lands on one node.
    * `require_all=True` waits for EVERY GPU node, which is right before Ray
      Train, since it places one worker per GPU.
    * `per_gpu=True` (default) scales each node's budget by the workers that
      will actually land on it, so an 8-GPU node asks for 8x what a single-GPU
      node does. Pass `per_gpu=False` for a flat per-node budget.
    * `num_workers` caps that multiplier at the number of workers the run
      actually requests, so pinning an 8-GPU cluster to 2 workers budgets for 2.

    Returns True once the cluster qualifies; False on timeout (caller decides).
    """
    import time
    gpus_by_host = {}
    if per_gpu:
        gpus_by_host = {
            n.get("NodeManagerHostname"): int(n.get("Resources", {}).get("GPU", 1))
            for n in ray_module.nodes()
            if n.get("Alive") and n.get("Resources", {}).get("GPU")
        }

    def _need(m):
        workers_here = max(1, gpus_by_host.get(m["host"], 1))
        if num_workers:
            workers_here = min(workers_here, max(1, int(num_workers)))
        return need_mib * workers_here

    deadline = time.time() + timeout_s
    while True:
        mem = node_host_memory(ray_module)
        short = [m for m in mem if m["available"] < _need(m)]
        ok = (not short) if require_all else (len(short) < len(mem))
        if mem and ok:
            scope = "all nodes" if require_all else "at least one node"
            worst = min(mem, key=lambda m: m["available"] - _need(m))
            log_fn(f"host headroom OK ({scope}): lowest is {worst['host']} with "
                   f"{worst['available']} MiB available (need {_need(worst)})")
            return True
        for m in short:
            log_fn(f"  WAITING on {m['host']}: {m['available']} MiB available of "
                   f"{m['total']} (shmem {m['shmem']} MiB) -- needs {_need(m)}")
        if time.time() >= deadline:
            log_fn(f"{len(short)} GPU node(s) still short of the load-spike "
                   f"budget ({need_mib} MiB per GPU worker) after "
                   f"{timeout_s}s. Proceeding, but a worker that dies here with "
                   f"'SYSTEM_ERROR ... connection error code 2' is the host OOM "
                   f"killer, not a bug in the training code. Idle Ray spill "
                   f"workers are the usual culprit -- restart the cluster to "
                   f"clear them, or stop the upstream stage from spilling.")
            return False
        time.sleep(poll_s)


def release_phase(ray_module, log_fn=print):
    """Drop local references and ask every GPU node to collect garbage.

    Called between phases (train -> serve -> sim) so the next phase starts
    without the previous one's plasma and idle spill workers still resident.
    """
    import gc
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    gc.collect()

    @ray_module.remote(num_cpus=0)
    def _gc():
        import gc as g
        g.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        return True

    nodes = [n for n in ray_module.nodes()
             if n.get("Alive") and n.get("Resources", {}).get("GPU")]
    ray_module.get([
        _gc.options(scheduling_strategy=NodeAffinitySchedulingStrategy(
            node_id=n["NodeID"], soft=False)).remote()
        for n in nodes
    ])
    log_fn(f"released phase state on {len(nodes)} GPU node(s)")


# ============================================================================
# Per-node HF snapshot staging (model only -- datasets are streamed via hf://)
# ============================================================================
def stage_model_to_local(source_uri, local_dir):
    """Sync a model/config dir from the public mirror to `local_dir` if not present.

    `source_uri` is a storage URI (or local directory). Skips the sync when config.json
    is already present (e.g. already staged on this node, or baked into the image).
    """
    local_dir = Path(local_dir)
    if (local_dir / "config.json").exists():
        return f"cached: {local_dir}"
    local_dir.mkdir(parents=True, exist_ok=True)
    source_str = str(source_uri)
    if os.path.isdir(source_str):
        import shutil
        shutil.copytree(source_str, local_dir, dirs_exist_ok=True)
        return f"copied from {source_str}: {local_dir}"
    elif source_str.startswith("gs://"):
        import subprocess
        subprocess.run(
            ["gcloud", "storage", "cp", "-r", f"{source_str.rstrip('/')}/*", str(local_dir)],
            check=True,
        )
        return f"downloaded from gcs: {local_dir}"
    else:
        import fsspec
        fs, fs_path = fsspec.core.url_to_fs(source_str)
        fs.get(fs_path, str(local_dir), recursive=True)
        return f"downloaded: {local_dir}"


def stage_on_all_nodes(ray_module, stage_fn, label, dest, log_fn=print):
    """Run stage_fn on the head node and every live GPU worker node.

    Each GPU node has its own /mnt/local_storage (per-node disk), so we
    pin a tiny num_cpus=0 task to each node and have it run the same
    snapshot_download call. log_fn defaults to print but can be log.info.
    """
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    log_fn(f"Staging {label} -> {dest} ...")
    log_fn(f"  on head: {stage_fn()}")

    nodes = [n for n in ray_module.nodes()
             if n.get("Alive") and n.get("Resources", {}).get("GPU")]

    @ray_module.remote(num_cpus=0)
    def _stage():
        return stage_fn()

    futures = [
        _stage.options(
            scheduling_strategy=NodeAffinitySchedulingStrategy(
                node_id=n["NodeID"], soft=False,
            )
        ).remote()
        for n in nodes
    ]
    for n, status in zip(nodes, ray_module.get(futures)):
        log_fn(f"  {n['NodeManagerHostname']}: {status}")
