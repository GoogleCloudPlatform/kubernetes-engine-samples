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

#reference: https://docs.nvidia.com/nemo/rl/0.3.0/guides/eval.html

#!/bin/bash
WANDB_API_KEY='WANDB_API_KEY' # Update this with your WANDB API key
HF_TOKEN='HF_TOKEN' # Update this with your HF token
WORLD_SIZE=8
DISTRIBUTED_CHECKPOINT_PATH="/data/nemo_rl_gemma3_27b_3_11" #Source Path of the NemoRL Distrbuted checkpoint
HUGGINGFACE_CHECKPOINT_PATH="/data/nemo_rl_gemma3_27b_3_11/hf3-11" #Destination path for converted HF Checkpoint


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

echo "Setting environment variables..."
export WANDB_API_KEY=$WANDB_API_KEY
export HF_TOKEN=$HF_TOKEN
export HF_HOME=/opt/nemo-rl/

###-----Example to launch Gemma3-27B on 1 node (8 GPUs)----------

uv run python examples/converters/convert_dcp_to_hf.py \
    --config $DISTRIBUTED_CHECKPOINT_PATH/step_10/config.yaml \
    --dcp-ckpt-path $DISTRIBUTED_CHECKPOINT_PATH/step_10/policy/weights/ \
    --hf-ckpt-path $HUGGINGFACE_CHECKPOINT_PATH


echo "--- Job Finished ---"
EOF
)

# --- Step 3: Execute the Job ---
echo "Submitting job to $HEAD_POD_NAME..."
echo "$JOB_SCRIPT" | tr -d '\r' | kubectl exec -i $HEAD_POD_NAME -c ray-head -- /bin/bash

echo ""
echo "Job submission complete."

# ----output-------
# + export HF_HOME=/opt/nemo-rl/
# + HF_HOME=/opt/nemo-rl/
# Setting environment variables...
# + uv run python examples/converters/convert_dcp_to_hf.py --config /data/nemo_rl_gemma3_25b_2_27/step_10/config.yaml --dcp-ckpt-path /data/nemo_rl_gemma3_25b_2_27/step_10/policy/weights/ --hf-ckpt-path /data/gemma3-27b-s10-hf
#    Building nemo-rl @ file:///opt/nemo-rl
#       Built nemo-rl @ file:///opt/nemo-rl
# Uninstalled 1 package in 2ms
# Installed 1 package in 0.73ms
# Saved HF checkpoint to: /data/gemma3-27b-s10-hf
# + echo '--- Job Finished ---'
# --- Job Finished ---

# Job submission complete.


# /opt/nemo-rl# tree /data/gemma3-27b-s10-hf
# /data/gemma3-27b-s10-hf
# |-- chat_template.jinja
# |-- config.json
# |-- pytorch_model.bin
# |-- special_tokens_map.json
# |-- tokenizer.json
# `-- tokenizer_config.json

# 1 directory, 6 files


#working command:
#uv run python examples/converters/convert_dcp_to_hf.py     --config /data/nemo_rl_gemma3_25b_2_27/step_10/config.yaml     --dcp-ckpt-path /data/nemo_rl_gemma3_25b_2_27/step_10/policy/weights/     --hf-ckpt-path generation.model_name=/data/nemo_rl_gemma3_25b_2_27/hf2