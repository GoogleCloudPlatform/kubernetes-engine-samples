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

# [START gke_ai_ml_gke_ray_tpu_get_started_data_prepare_preference]
"""Prepare a DPO preference dataset for Qwen3-4B fine-tuning with Ray Data.

Ray Data is the scalable *data plane*: it streams the raw dataset, reshapes each
row into the columns Tunix's `DPOTrainer` expects, and writes clean JSONL to
GCS. Tokenization and the chat template happen in the trainer (../train/), not
here.

Source: HuggingFaceH4/ultrafeedback_binarized (MIT), a standard DPO preference
dataset in parquet, so Ray Data reads it directly over the `hf://` filesystem.
Its `chosen`/`rejected` are chat conversations ([{role, content}, ...]); we take
the final assistant turn as the response text.

Tunix DPO schema (tunix.sft.dpo.dpo_trainer.DPOTrainingConfig):
    prompts, chosen_responses, rejected_responses

Run it as a Ray job against the cluster head:

    ray job submit --address http://localhost:8265 --working-dir . -- \
        python prepare_preference_data.py --output gs://BUCKET_NAME/ufb-dpo
"""
import argparse
from typing import Any

import ray

# Point at the explicit shard. read_parquet doesn't glob wildcards over hf://.
DATA_FILES = (
    "hf://datasets/HuggingFaceH4/ultrafeedback_binarized/"
    "data/train_prefs-00000-of-00001.parquet"
)


def _assistant_text(conversation: Any) -> str:
    """Returns the last assistant message's content from a chat list.

    Args:
        conversation: A chat list of ``{role, content}`` turns, or any value
            (non-lists yield an empty string).

    Returns:
        The final assistant turn's text, or "" if there is none.
    """
    if not isinstance(conversation, (list, tuple)):
        return ""
    for turn in reversed(conversation):
        if isinstance(turn, dict) and turn.get("role") == "assistant":
            return (turn.get("content") or "").strip()
    return ""


def to_dpo(row: dict) -> dict:
    """Reshapes one ultrafeedback row into Tunix's DPO columns (distributed).

    Args:
        row: One raw ultrafeedback record (prompt, chosen, rejected).

    Returns:
        A dict with ``prompts``, ``chosen_responses``, ``rejected_responses``.
    """
    return {
        "prompts": (row.get("prompt") or "").strip(),
        "chosen_responses": _assistant_text(row.get("chosen")),
        "rejected_responses": _assistant_text(row.get("rejected")),
    }


def is_valid(row: dict) -> bool:
    """Reports whether a reshaped row is usable for DPO.

    Args:
        row: A reshaped row with the three Tunix DPO columns.

    Returns:
        True unless a field is empty or chosen == rejected (no signal).
    """
    return bool(
        row["prompts"]
        and row["chosen_responses"]
        and row["rejected_responses"]
        and row["chosen_responses"] != row["rejected_responses"]
    )


def main() -> None:
    """Prepares the DPO JSONL and writes it to the output path."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for the DPO JSONL (e.g. gs://bucket/ufb-dpo)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Cap rows for a quick get-started run (0 = full split)",
    )
    args = parser.parse_args()

    ray.init()

    ds = ray.data.read_parquet(DATA_FILES)
    if args.limit:
        ds = ds.limit(args.limit)

    ds = ds.map(to_dpo).filter(is_valid)

    num_records = ds.count()
    print(f"Prepared {num_records} DPO records")
    print("Sample row:", ds.take(1)[0])

    ds.write_json(args.output)
    print(f"Wrote DPO JSONL to {args.output}")

    ray.shutdown()


if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_tpu_get_started_data_prepare_preference]
