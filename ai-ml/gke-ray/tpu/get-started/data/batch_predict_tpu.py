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

# [START gke_ai_ml_gke_ray_tpu_get_started_data_batch_predict_tpu]
"""Offline batch prediction on a TPU slice with Ray Data `iter_jax_batches`.

This is the batch (offline) counterpart to the online Ray Serve endpoint in
../serve. Instead of one request at a time over HTTP, it streams a whole dataset
through the model on the TPU. The mechanic that makes this work is Ray Data's
``iter_jax_batches``: it yields batches as JAX arrays already sharded across the
slice's chips, so the data pipeline (read + tokenize, distributed on CPU) and
the model forward pass (on TPU) overlap without you writing any
device-placement code.

Flow:
  read prompts (Ray Data)  ->  tokenize to int32 ids (CPU, distributed)
    ->  streaming_split across TPU hosts
    ->  iter_jax_batches on each host  ->  Qwen3 forward pass (TPU)
    ->  argmax next-token  ->  write predictions (GCS)

The model is the Qwen3-4B we fine-tuned in ../train (base safetensors + the DPO
LoRA adapter restored from the orbax checkpoint). Pass --ckpt-dir to load the
fine-tuned adapter; omit it to run the base model.

Submit as a Ray job against the cluster head:

    ray job submit --address http://localhost:8265 --working-dir . \
      --runtime-env-json '{"env_vars":{"JAX_PLATFORMS":"tpu,cpu"}}' -- \
      python batch_predict_tpu.py \
        --input /data/ufb-dpo \
        --model-dir /data/models/qwen3-4b-2507 \
        --ckpt-dir /data/ckpts/qwen3-dpo \
        --output /data/predictions/qwen3-dpo
"""
import argparse
import functools
import json
import os
from typing import Any

import ray

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507")
CHIPS_PER_HOST = int(os.environ.get("CHIPS_PER_HOST", "8"))
MAX_LEN = int(os.environ.get("MAX_LEN", "256"))


@functools.cache
def _load_tokenizer(model_id: str) -> Any:
    """Loads and caches one left-padded tokenizer per worker process.

    Args:
        model_id: Hugging Face model id whose tokenizer to load.

    Returns:
        The cached ``AutoTokenizer`` for ``model_id``.
    """
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    # Left-pad so greedy decode appends after the prompt (right-pad breaks it).
    tokenizer.padding_side = "left"
    return tokenizer


def tokenize(row: dict) -> dict:
    """Turn one row into padded int32 token ids + a mask (CPU, distributed).

    iter_jax_batches carries only numeric arrays, so the prompt text is
    tokenized here (in Ray Data, spread across CPU workers) and the model reads
    ids on TPU. We keep the raw prompt out of the batch and re-attach it after
    prediction by row order within each shard.

    Args:
        row: One input record with a ``prompts`` string field.

    Returns:
        A dict with int32 ``input_ids`` and ``attention_mask`` arrays.
    """
    import numpy as np

    tokenizer = _load_tokenizer(MODEL_ID)
    messages = [{"role": "user", "content": row["prompts"]}]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    enc = tokenizer(
        text,
        truncation=True,
        max_length=MAX_LEN,
        padding="max_length",
        return_tensors="np",
    )

    return {
        "input_ids": enc["input_ids"][0].astype(np.int32),
        "attention_mask": enc["attention_mask"][0].astype(np.int32),
    }


@ray.remote(resources={"TPU": CHIPS_PER_HOST})
def predict_on_host(
    shard_ds: "ray.data.DataIterator",
    *,
    batch_size: int,
    model_dir: str,
    ckpt_dir: str,
    out_path: str,
    max_new_tokens: int,
) -> str:
    """Loads the model once, then streams device-sharded batches and predicts.

    Runs on one TPU host. Ray Data's iter_jax_batches yields JAX arrays already
    sharded across this host's chips; the forward pass consumes them directly.

    Args:
        shard_ds: This host's shard of the tokenized dataset.
        batch_size: Rows per device batch.
        model_dir: Path to the base model safetensors.
        ckpt_dir: DPO LoRA checkpoint dir, or "" to run the base model.
        out_path: Directory for this host's predictions JSONL shard.
        max_new_tokens: Greedy-decode length.

    Returns:
        A one-line summary of the host id, device count, and rows written.
    """
    import jax
    import jax.numpy as jnp
    import numpy as np

    from tunix.models.qwen3 import model as qwen3_model_lib
    from tunix.models.qwen3 import params as params_lib

    # Pure-FSDP mesh. Params and batches shard the same axis (on-device).
    mesh = jax.make_mesh(
        (jax.device_count(), 1),
        ("fsdp", "tp"),
        axis_types=(jax.sharding.AxisType.Auto,) * 2,
    )

    model_config = qwen3_model_lib.ModelConfig.qwen3_4b_instruct_2507()
    with mesh:
        model = params_lib.create_model_from_safe_tensors(
            model_dir, model_config, mesh
        )

    # Restore via Tunix's CheckpointManager. It matches the saved LoRA-only
    # tree (hand-rolled orbax args break).
    if ckpt_dir:
        import qwix
        from tunix.sft.checkpoint_manager import CheckpointManager

        lora_provider = qwix.LoraProvider(
            module_path=(
                ".*q_proj|.*k_proj|.*v_proj|.*o_proj|"
                ".*gate_proj|.*up_proj|.*down_proj"
            ),
            rank=16,
            alpha=32.0,
        )
        # Apply LoRA outside the mesh. The batch-2 dummy from get_model_input()
        # hits IndivisibleError on an 8-way FSDP mesh. qwix only traces shapes.
        model = qwix.apply_lora_to_model(
            model, lora_provider, **model.get_model_input()
        )
        # maybe_restore mutates LoRA params in place (trainer saved LoRA-only).
        ckpt_mgr = CheckpointManager(ckpt_dir)
        with mesh:
            step, _ = ckpt_mgr.maybe_restore(
                model, restore_only_lora_params=True
            )
        ckpt_mgr.close()
        print(f"restored DPO adapter from {ckpt_dir} step={step}", flush=True)

    tokenizer = _load_tokenizer(MODEL_ID)

    from flax import nnx

    # nnx.jit (not jax.jit) so the traced fn can hold the nnx model.
    @nnx.jit
    def next_token(model, input_ids, attn):
        # positions come from the cumulative mask so real tokens start at 0.
        # No cache means a full forward pass. mask broadcasts to (B, 1, T).
        _, t = input_ids.shape
        positions = jnp.clip(jnp.cumsum(attn, axis=1) - 1, 0, t - 1)
        mask = attn.astype(jnp.bool_)[:, None, :]
        logits, _ = model(input_ids, positions, None, mask)
        # Left-padding keeps a real token in the last column, so predict there.
        return jnp.argmax(logits[:, -1], axis=-1)  # (B,)

    def generate(input_ids, attn, max_new_tokens):
        # Basic greedy decode (no KV cache) for readability.
        ids, mask = input_ids, attn
        new_cols = []
        for _ in range(max_new_tokens):
            nxt = np.asarray(next_token(model, ids, mask))
            new_cols.append(nxt)
            nxt = nxt[:, None]
            ids = np.concatenate([ids, nxt], axis=1)
            mask = np.concatenate([mask, np.ones_like(nxt)], axis=1)
        if not new_cols:
            return np.zeros((len(input_ids), 0))
        return np.stack(new_cols, axis=1)

    n_rows = 0
    preds = []
    for batch in shard_ds.iter_jax_batches(batch_size=batch_size):
        in_ids = np.asarray(batch["input_ids"])
        attn = np.asarray(batch["attention_mask"])
        gen = generate(in_ids, attn, max_new_tokens)
        for row_ids, row_mask, row_gen in zip(in_ids, attn, gen, strict=True):
            # Strip pad ids so each output row is self-contained.
            real = row_ids[row_mask.astype(bool)]
            prompt_txt = tokenizer.decode(real, skip_special_tokens=True)
            completion = tokenizer.decode(
                row_gen.astype(int), skip_special_tokens=True
            )
            preds.append({"prompt": prompt_txt, "prediction": completion})
        n_rows += in_ids.shape[0]

    # out_path is under gcsfuse /data, so shards land in GCS.
    wid = os.environ.get("TPU_WORKER_ID", "0")
    shard_file = os.path.join(out_path, f"predictions-host{wid}.jsonl")
    os.makedirs(out_path, exist_ok=True)
    with open(shard_file, "w") as f:
        for row in preds:
            f.write(f"{json.dumps(row)}\n")

    return (
        f"host TPU_WORKER_ID={wid} devices={jax.device_count()} "
        f"rows={n_rows} wrote={shard_file}"
    )


def main() -> None:
    """Runs batch prediction across TPU hosts and writes JSONL shards."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input", required=True, help="Prompt JSONL dir (gs:// or /data)"
    )
    parser.add_argument("--model-dir", default="/data/models/qwen3-4b-2507")
    parser.add_argument(
        "--ckpt-dir", default="", help="DPO ckpt dir (empty = base model)"
    )
    parser.add_argument("--output", default="/data/predictions/qwen3-dpo")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument(
        "--max-new-tokens", type=int, default=24, help="greedy decode length"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="cap rows for a quick run"
    )
    args = parser.parse_args()

    ray.init()

    ds = ray.data.read_json(args.input)
    if args.limit:
        ds = ds.limit(args.limit)
    ds = ds.map(tokenize)

    num_hosts = int(ray.available_resources().get("TPU", 0)) // CHIPS_PER_HOST
    print(f"TPU hosts available: {num_hosts}")

    shards = ds.streaming_split(num_hosts, equal=True)
    results = ray.get([
        predict_on_host.remote(
            shard,
            batch_size=args.batch_size,
            model_dir=args.model_dir,
            ckpt_dir=args.ckpt_dir,
            out_path=args.output,
            max_new_tokens=args.max_new_tokens,
        )
        for shard in shards
    ])
    for result in results:
        print(result)

    ray.shutdown()


if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_tpu_get_started_data_batch_predict_tpu]
