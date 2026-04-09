# Copyright 2026 Google LLC
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

#!/bin/bash
WANDB_API_KEY='YOUR_WANDB_API_KEY' # Update this with your WANDB API key
HF_TOKEN='YOUR_HF_TOKEN' # Update this with your HF token
WORLD_SIZE=16

# --- Step 1: Find the Ray Head Pod ---
echo "Finding Ray head pod..."
export HEAD_POD_NAME=$(kubectl get pods --selector=ray.io/node-type=head -o jsonpath='{.items[0].metadata.name}')
if [ -z "$HEAD_POD_NAME" ]; then
    echo "Error: No running Ray head pod found. Please check your cluster."
    exit 1
fi
echo "Found head pod: $HEAD_POD_NAME"
echo ""

# --- Step 2: Define the Job Script to Run ---
# This is the script that will be executed *inside* the head pod.
# It assumes the 'uv venv' setup from the values.yaml is already done.
JOB_SCRIPT=$(cat <<EOF
set -ex

echo "--- Running on Ray Head Pod ($HOSTNAME) ---"
cd /opt/nemo-rl

git pull && git checkout main

sed -i 's/subset: Optional\[str\] = None/subset: Optional[str] = "main"/' /opt/nemo-rl/nemo_rl/data/datasets/response_datasets/response_dataset.py
sed -i 's/raw_dataset = load_dataset(data_path)/raw_dataset = load_dataset(data_path, "main")/' /opt/nemo-rl/nemo_rl/data/datasets/utils.py

echo "Setting environment variables..."
export WANDB_API_KEY=$WANDB_API_KEY
export HF_TOKEN=$HF_TOKEN
export HF_HOME=/opt/nemo-rl/

###-----Example to launch Gemma3-27B on 3 nodes (24 GPUs)----------
uv run python examples/run_grpo_math.py \
  --config examples/configs/recipes/llm/grpo-gemma3-27b-it-8n4g-fsdp2tp4-actckpt-long.yaml \
  cluster.num_nodes=2 \
  cluster.gpus_per_node=8 \
  grpo.max_num_steps=300 \
  checkpointing.checkpoint_dir=/data/nemo_rl_gemma3_27b_3_17 \
  data.dataset_name=ResponseDataset \
  +data.train_data_path=openai/gsm8k \
  +data.val_data_path=openai/gsm8k \
  +data.val_split=test \
  +data.train_split=train \
  +data.subset="main" \
  +data.input_key="question" \
  +data.output_key="answer" \
  logger.tensorboard_enabled=False \
  logger.wandb_enabled=True \
  logger.wandb.name='nemo_rl_gemma3_27b_3_17' \
  grpo.num_prompts_per_step=16 \
  grpo.num_generations_per_prompt=64 \
  policy.generation.colocated.enabled=False \
  policy.generation.colocated.resources.num_nodes=1 \
  policy.generation.colocated.resources.gpus_per_node=8 \
  policy.generation.vllm_cfg.tensor_parallel_size=8 \
  policy.generation.vllm_cfg.gpu_memory_utilization=0.9 \
  policy.dtensor_cfg.tensor_parallel_size=8

echo "--- Job Finished ---"
EOF
)

# --- Step 3: Execute the Job ---
echo "Submitting job to $HEAD_POD_NAME..."
echo "$JOB_SCRIPT" | tr -d '\r' | kubectl exec -i $HEAD_POD_NAME -c ray-head -- /bin/bash

echo ""
echo "Job submission complete."
