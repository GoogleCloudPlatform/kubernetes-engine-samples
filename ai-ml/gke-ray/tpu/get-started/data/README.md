# Prepare data and batch-predict on TPU with Ray Data

Two things Ray Data does around a TPU fine-tune, both distributed on CPU:

- **Prepare** (`prepare_preference_data.py`) streams a raw preference dataset,
  reshapes it into the columns Tunix's `DPOTrainer` expects, and writes clean JSONL
  to GCS. This is the input to the [train](../train/) sample.
- **Batch-predict** (`batch_predict_tpu.py`) runs offline inference on the slice:
  it streams prompts through the model with `iter_jax_batches`, which hands each TPU
  host batches that are already device-sharded JAX arrays, then writes the
  predictions back to GCS.

This is the **data** sample in the Ray-on-TPU get-started set. It runs against the
cluster from [`../cluster/`](../cluster/).

## Prerequisites

Before you run the data jobs, make sure you have:

- A cluster from [`../cluster/`](../cluster/) up and running.
- A **Ray head to submit to** (`ray job submit`). Prepare is CPU-only and can use
  any running RayCluster or RayService (for example serve's `qwen3-serve`).
  **Batch prediction** needs the [train](../train/) RayCluster (`qwen3-dpo`),
  which gcsfuse-mounts the bucket at `/data` and holds the TPU slice. Set
  `RAY_CLUSTER_NAME` to whichever you use.
- `kubectl` and the Ray CLI (`pip install ray`).

## Dataset

[`HuggingFaceH4/ultrafeedback_binarized`](https://huggingface.co/datasets/HuggingFaceH4/ultrafeedback_binarized)
(MIT) is a standard DPO preference dataset in **parquet**, so Ray Data reads it
directly over the `hf://` filesystem. Its `chosen`/`rejected` are chat
conversations; the prep takes the final assistant turn as the response text and
emits the Tunix DPO schema: `prompts`, `chosen_responses`, `rejected_responses`.

> Note:
> Pick a dataset that streams. `ultrafeedback_binarized` is natively parquet, so
> `read_parquet` reads it directly over `hf://` with no download step. Datasets
> that ship as zip archives (many multimodal sets) can't be streamed the same way.
> Check the on-disk format before you commit to one.

## Prepare the data

Submit the prep job:

```bash
# port-forward the Ray head dashboard
kubectl port-forward svc/RAY_CLUSTER_NAME-head-svc 8265:8265 &

ray job submit --address http://localhost:8265 --working-dir . -- \
  python prepare_preference_data.py \
    --output gs://BUCKET_NAME/ufb-dpo --limit 2000
```

### What you should see

The job reads the parquet over `hf://`, filters rows where chosen == rejected,
and writes JSONL to GCS:

```text
Prepared 197 DPO records
Sample row: {'prompts': '...', 'chosen_responses': '...', 'rejected_responses': '...'}
Wrote DPO JSONL to gs://BUCKET_NAME/ufb-dpo
```

Each record has exactly the three columns the [train](../train/) sample's
`DPOTrainer` consumes.

## Batch prediction

`batch_predict_tpu.py` is the offline counterpart to the online [serve](../serve/)
endpoint: instead of one request at a time over HTTP, it streams a whole dataset
of prompts through the model on the TPU. `iter_jax_batches` yields batches as JAX
arrays already sharded across the slice's chips, so the read + tokenize pipeline
(CPU) overlaps with the forward pass (TPU) with no device-placement code.

Point it at the [train](../train/) sample's DPO checkpoint to run the fine-tuned
model (omit `--ckpt-dir` to run the base model):

```bash
ray job submit --address http://localhost:8265 --working-dir . \
  --runtime-env-json '{"env_vars":{"JAX_PLATFORMS":"tpu,cpu"}}' -- \
  python batch_predict_tpu.py \
    --input /data/ufb-dpo \
    --model-dir /data/models/qwen3-4b-2507 \
    --ckpt-dir /data/ckpts/qwen3-dpo \
    --output /data/predictions/qwen3-dpo
```

Each TPU host writes a `predictions-host*.jsonl` shard to the output path (under
the gcsfuse `/data` mount, so it lands in GCS). Read one back with
`gcloud storage cat`.

## How it works

Starting from ingesting data, below you have the process:

- `ray.data.read_parquet("hf://datasets/.../train_prefs-*.parquet")` streams the
  dataset (point at the explicit shard because Ray Data doesn't glob wildcards over
  `hf://`).
- `.map(to_dpo).filter(is_valid)` reshapes + cleans, distributed on CPU.
- `ds.write_json("gs://...")` writes the trainer's input.
- Batch predict adds `ds.streaming_split(num_hosts)` + `iter_jax_batches` to fan
  the data across TPU hosts as device-sharded JAX arrays.

> Note:
> Writing to GCS needs `storage.buckets.get` (pyarrow's GCS driver calls
> `GetBucketMetadata`), which `roles/storage.objectAdmin` alone doesn't grant.
> The cluster Terraform also binds `roles/storage.legacyBucketReader` on the data
> bucket for the workload SA.

## Next

- **[train](../train/)**. DPO fine-tune Qwen3-4B on the prepared JSONL.
- **[cluster/monitoring](../cluster/#monitoring)**. Watch TPU utilization while jobs run.
