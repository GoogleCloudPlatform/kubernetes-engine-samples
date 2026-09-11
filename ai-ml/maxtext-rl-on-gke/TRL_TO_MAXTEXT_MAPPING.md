# TRL to MaxText GRPO Configuration Mapping

When migrating GRPO training from Hugging Face TRL (Transformer Reinforcement Learning) on GPUs (e.g., H100/H200) to MaxText on Google Cloud TPUs, many hyperparameters map directly, while others require architectural adjustments due to the nature of TPU static graphs and synchronous data parallelism.

---

## 1. Direct Configuration Mapping

### TRL (Hugging Face) Configuration
Below is a standard TRL configuration block for GRPO training:

```yaml
# trl_config.yaml
training:
  num_train_epochs: 3
  learning_rate: 0.000001
  warmup_ratio: 0.03
  lr_scheduler_type: cosine
  max_grad_norm: 1.0          # Defaults to 1.0 in TRL
  save_steps: 100
  logging_steps: 10
  per_device_train_batch_size: 16
  gradient_accumulation_steps: 6
  gradient_checkpointing: true
  max_completion_length: 512
  num_generations: 8
  beta: 0.001
  bf16: true
  do_eval: false
  eval_steps: 50
  epsilon_high: 0.2           # Defaults to 0.2
```

### MaxText (TPU) Command Equivalent
Here is how those exact parameters translate into MaxText command-line overrides. 
*(Note: Batch size assumes an 8-device TPU topology like `v7x-2x2x1`. Total Batch = 16 per device * 6 accum * 8 devices = 768).*

```bash
# MaxText equivalent command arguments
python3 -m maxtext.trainers.post_train.rl.train_rl maxtext/configs/post_train/rl.yml \
  num_epoch=3 \
  learning_rate=1e-6 \
  warmup_steps_fraction=0.03 \
  gradient_clipping_threshold=1.0 \
  checkpoint_period=100 \
  log_period=10 \
  batch_size=48 \
  train_micro_batch_size=8 \
  rollout_micro_batch_size=16 \
  max_prefill_predict_length=2900 \
  max_target_length=3412 \
  num_generations=8 \
  grpo_beta=0.001 \
  grpo_epsilon=0.2 \
  weight_dtype=bfloat16 \
  num_test_batches=0 \
  eval_interval=0
```

### Critical Translation "Gotchas"

**1. Batch Size Counts Prompts, Not Completions**
* **TRL**: `per_device_train_batch_size` counts **completions**. (e.g. 16 completions * 6 grad accum * 4 GPUs = 384 total completions. 384 / 8 generations = 48 unique prompts).
* **MaxText**: `batch_size` counts **unique prompts**. MaxText/Tunix repeats each prompt `num_generations` times. To get H200 parity with 384 completions, you must set `batch_size=48` (48 prompts x 8 generations = 384 completions). Setting `batch_size=384` would result in 3,072 completions per step and cause an immediate Out of Memory (OOM) error.

**2. Sequence Length Padding causes OOMs**
* **TRL**: Dynamically pads to the batch max. You can set a high `max_prompt_length` and it only uses what it needs.
* **MaxText**: Statically left-pads *every* prompt to `max_prefill_predict_length`. Every sequence in the reference log-prob pass is padded to exactly `max_target_length`. If you blindly set `max_target_length=8192`, it doubles the `[B, T, V]` logits tensor and causes an HBM OOM. 
  * *Formula*: `max_target_length` = `max_prefill_predict_length` + `completion length`. Keep these as tight to your dataset max as possible (e.g. 2900 + 512 = 3412).

**3. train_micro_batch_size determines Accumulation Steps**
* If left unset, it falls back to `batch_size`. Running 48 prompts x 8 generations = 384 sequences in one logps pass will cause an immediate HBM OOM. Set it explicitly (e.g. `8`) so it processes `8 x 8 = 64` sequences per pass. This controls accumulation granularity.


*(Note on Lengths: `max_target_length` in MaxText is the total sequence length. If your max prompt is 512 and your max completion is 512, set `max_prefill_predict_length=512` and `max_target_length=1024`)*.

---

## 2. Configurations Not Directly Translated

Because TPUs require statically compiled graphs (XLA) and handle distributed memory globally rather than per-device, some TRL parameters do not have a 1-to-1 equivalent in MaxText.

```text
group_by_length: false        # Not applicable: TPUs require strictly static graph shapes, making dynamic length grouping irrelevant.
dataloader_drop_last: true    # Not explicitly toggleable: MaxText's static shape compiler dynamically pads or drops remainders to fit the global batch size.
per_device_train_batch_size   # Architecturally different: MaxText defines one global `batch_size` across the entire pod, rather than a per-device micro-batch size.
loss_type: null               # Bounded support: MaxText natively implements standard 'grpo' and 'gspo-token'; it lacks custom community variants like 'dr_grpo'.
```
