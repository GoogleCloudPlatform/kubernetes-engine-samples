# Custom Dataset & Reward Functions Guide for MaxText GRPO (TPU v7x / v6e)

This guide explains how to train **MaxText Group Relative Policy Optimization (GRPO)** using your own **preprocessed Hugging Face dataset** and **custom Python reward functions** on Google Cloud TPUs via Kubernetes (GKE).

---

## 1. Where to Create & Place the Custom Reward Function File

MaxText dynamically imports reward functions at runtime using standard Python filesystem paths. You have three flexible options to provide the `custom_rewards.py` file to the training pod:

### Option A: Store on your Mounted PVC / Cloud Storage Bucket (Recommended)
Place `custom_rewards.py` directly alongside your dataset or checkpoint directory inside your Cloud Storage bucket or PersistentVolume:
* **GCS Bucket Path**: `gs://your-checkpoint-or-data-bucket/scripts/custom_rewards.py`
* **Container Path (via PVC mount)**: `/checkpoint/scripts/custom_rewards.py` or `/data/custom_rewards.py`

### Option B: Mount via Kubernetes ConfigMap (No GCS upload required)
Create a Kubernetes ConfigMap containing your Python reward script, run this command on your terminal:
```bash
kubectl create configmap grpo-custom-rewards \
  --from-file=custom_rewards.py=./custom_rewards.py \
  --namespace=default
```
Once the configmap is created we can mount the ConfigMap in your JobSet YAML file as a volume mount:
```yaml
volumeMounts:
- name: reward-script-volume
  mountPath: /app/custom_rewards.py
  subPath: custom_rewards.py
volumes:
- name: reward-script-volume
  configMap:
    name: grpo-custom-rewards
```

### Option C: Bake into the Container Image
Copy the script into your Docker container during `docker build`:
```dockerfile
COPY custom_rewards.py /workspace/custom_rewards.py
```

---

## 2. Custom Reward Function Specification

MaxText expects each reward function in your Python file to match this exact signature:

```python
def your_reward_fn(
    prompts: list[str],
    completions: list[str],
    tmvp_config: Any,
    **kwargs
) -> list[float]:
```

* **`prompts`** (`list[str]`): Batch of prompt strings sent to the model.
* **`completions`** (`list[str]`): Batch of candidate generated responses ($G$ generations per prompt).
* **`tmvp_config`** (`Any`): The active MaxText config object (access hyperparameters or custom thresholds).
* **`kwargs`**: Keyword arguments containing extra dataset columns (e.g. `kwargs.get("answer")` contains ground-truth targets if available).
* **Return Value** (`list[float]`): A list of scalar float reward scores, exactly matching `len(completions)`.

---

## 3. Reference Reward Script (`custom_rewards.py`)

Create this file and save it to your chosen location (e.g. `/data/custom_rewards.py`):

```python
"""Custom reward functions for MaxText GRPO RL post-training."""
import re
from typing import Any, Sequence

def format_reward(
    prompts: Sequence[str],
    completions: Sequence[str],
    tmvp_config: Any = None,
    **kwargs
) -> list[float]:
    """Rewards adherence to thinking/reasoning tags: <reasoning>...</reasoning><answer>...</answer>"""
    rewards = []
    pattern = r"<reasoning>.*?</reasoning>\s*<answer>.*?</answer>"
    
    for completion in completions:
        match = re.search(pattern, completion, re.DOTALL)
        if match:
            rewards.append(1.0)
        else:
            rewards.append(0.0)
    return rewards


def exact_match_reward(
    prompts: Sequence[str],
    completions: Sequence[str],
    tmvp_config: Any = None,
    **kwargs
) -> list[float]:
    """Compares the extracted solution against the ground truth answer."""
    rewards = []
    # Ground truth answers passed from the preprocessed dataset
    answers = kwargs.get("answer", [])
    
    for i, completion in enumerate(completions):
        score = 0.0
        # Extract content between <answer>...</answer> tags
        if "<answer>" in completion and "</answer>" in completion:
            extracted = completion.split("<answer>")[-1].split("</answer>")[0].strip()
            
            # If ground truth answer list exists, verify match
            if i < len(answers) and answers[i] is not None:
                gold_answer = str(answers[i]).strip()
                if extracted.lower() == gold_answer.lower():
                    score = 2.0
            else:
                # Rule-based fallback if no ground-truth column
                if len(extracted) > 0:
                    score = 1.0
                    
        rewards.append(score)
    return rewards
```

---

## 4. Preprocessed Hugging Face Dataset Setup

Store your preprocessed dataset on your mounted PVC directory (e.g. `/data/`).

### Supported Formats on PVC:
1. **Parquet Directory / Files** (Recommended): `/data/train.parquet` (or `/data/train-*.parquet`)
2. **JSON / JSONL Files**: `/data/train.jsonl`
3. **Hugging Face `save_to_disk` Folder**: Directory generated via `dataset.save_to_disk('/data/hf_dataset')`

### Column Requirements:
MaxText's built-in processor automatically reads:
* **Prompt Column**: `prompt`, `question`, or `problem`
* **Answer Column**: `answer`, `solution`, or `expected_answer`

---

## 5. Kubernetes JobSet Configuration

Update lines 71–85 in your JobSet manifest ([`llama3.1-8b-grpo-dws-2x2x1-training.yaml`](llama3.1-8b-grpo-dws-2x2x1-training.yaml)):
> **Note**: Remember to replace all placeholders enclosed in `<...>` (e.g. `<YOUR_REGION>`, `<YOUR_PROJECT_ID>`, `<YOUR_REPO_NAME>`, `<YOUR_CHECKPOINT_PVC_NAME>`, and `<YOUR_DATASET_PVC_NAME>`) with your actual configuration values. Also, this yaml file uses Option A by using custom rewards function stored in GCS Bucket and mounted as a volume mount.

```yaml
            volumeMounts:
            - mountPath: /dev/shm
              name: dshm
            - mountPath: /checkpoint
              name: gcs-input
            - mountPath: /data                 # <-- Mount PVC containing dataset and custom_rewards.py
              name: dataset-volume
            containers:
            - name: grpo-trainer
              image: <YOUR_REGION>-docker.pkg.dev/<YOUR_PROJECT_ID>/<YOUR_REPO_NAME>/maxtext-grpo-runner:v2
              command:
              - python3
              - -m
              - maxtext.trainers.post_train.rl.train_rl
              - maxtext/configs/post_train/rl.yml
              - model_name=llama3.1-8b-Instruct
              - tokenizer_path=meta-llama/Llama-3.1-8B-Instruct
              - run_name=llama3-1-8b-grpo-custom-run
              - base_output_directory=/checkpoint/maxtext
              - chips_per_vm=4
              # ==========================================================
              # 1. Custom Dataset on PVC
              # ==========================================================
              - hf_train_files=/data/train.parquet       # Or dataset_name=/data/hf_dataset
              - hf_eval_files=/data/test.parquet         # Optional eval split
              - train_split=train
              - eval_split=test
              - max_prefill_predict_length=512           # Max input prompt token length
              - max_target_length=2048                  # Total sequence length (prompt + output)
              # ==========================================================
              # 2. Custom Reward Functions
              # ==========================================================
              - reward_functions_path=/data/custom_rewards.py
              - reward_functions=format_reward,exact_match_reward
              # ==========================================================
              # 3. GRPO Hyperparameters
              # ==========================================================
              - num_batches=1000                        # Total training steps
              - num_generations=4                       # Rollout group size G (4 or 8)
              - grpo_beta=0.08                          # KL divergence regularizer
          volumes:
          - name: dshm
            emptyDir:
              medium: Memory
          - name: gcs-input
            persistentVolumeClaim:
              claimName: <YOUR_CHECKPOINT_PVC_NAME>
          - name: dataset-volume
            persistentVolumeClaim:
              claimName: <YOUR_DATASET_PVC_NAME>
```

---

## 6. How to Verify Execution

When you submit the job:
```bash
kubectl apply -f llama3.1-8b-grpo-dws-2x2x1-training.yaml
```

Check the trainer pod logs to verify that MaxText has detected and loaded your custom reward functions:
```bash
kubectl logs -l app=llama3-1-8b-grpo-training -c grpo-trainer -f
```

You should see log entries confirming:
```
INFO: reward_fns: using 2 custom reward function(s) ['format_reward', 'exact_match_reward'] from /data/custom_rewards.py
INFO: Loaded Hugging Face dataset from /data/train.parquet with split train.
```
