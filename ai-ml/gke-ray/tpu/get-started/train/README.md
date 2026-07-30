# DPO fine-tune Qwen3-4B on a TPU slice with Ray Train and Tunix

Preference-tune
[`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
(a small, text-only LLM, Apache-2.0) on a Cloud TPU v6e slice using **Ray Train's
`JaxTrainer`** for TPU orchestration and **Tunix's `DPOTrainer`** for the
preference optimization, with **qwix LoRA**.

The sample consumes the
preference JSONL produced by [`../data/`](../data/) and runs on the cluster from
[`../cluster/`](../cluster/).

## Why this stack

The sample uses the following frameworks:

- **Ray Train `JaxTrainer`** reserves the slice, starts one worker per host, and
  wires the JAX distributed runtime. You declare a topology, not placement code.
- **Tunix `DPOTrainer`** (`tunix.sft.dpo.dpo_trainer`) holds a frozen reference
  model and optimizes the DPO loss over `{prompts, chosen_responses,
rejected_responses}`. Qwen3-4B has a JAX-native Tunix implementation
  (`tunix/models/qwen3/`) with a `qwen3_4b_instruct_2507()` config, so it trains
  natively on TPU (no PyTorch bridge).
- **qwix LoRA** trains a small adapter on the policy model; the reference stays
  frozen.

> Note:
> Qwen3-4B has a JAX-native implementation on _both_ Ray-on-TPU paths: serving in
> vLLM-TPU **and** training in Tunix. That is the key model-selection decision.
> The same model serves ([serve](../serve/)) and DPO-trains here, with no PyTorch
> fallback on either side.

## Prerequisites

Before you launch the DPO run, make sure you have:

1. **Cluster** with a v6e slice + GCS FUSE CSI driver ([`../cluster/`](../cluster/)).
2. **Training image** with vLLM-TPU nightly + Tunix + grain (see `Dockerfile`). Build
   it with `cloudbuild.yaml`:

   ```bash
   gcloud builds submit --config cloudbuild.yaml \
     --substitutions=_IMAGE=REGION-docker.pkg.dev/PROJECT_ID/ray-tpu/ray-tpu-train:v1 .
   ```

   `cloudbuild.yaml` also stages the model to GCS **in parallel** with the image
   build (image build and model download start concurrently via `waitFor: ["-"]`;
   a final cloud-sdk step uploads the weights to the bucket).

3. **Prepared data**. Run [`../data/prepare_preference_data.py`](../data/) to
   write the preference JSONL to your bucket.

## About the base image

The image is a pinned nightly, `vllm/vllm-tpu:nightly-20260701-6af3d12-9969466`,
which bundles Ray 2.56 (`ray.train.v2.jax`), qwix, flax, and transformers on TPU.
The tagged `rayproject/ray:*-tpu` hit numpy and protobuf version skew, so the
nightly is the working base. `Dockerfile` adds Tunix and grain and pins protobuf
to the 6.x line (Tunix needs `>=6.31`, the opposite of the serve image's `<6`).

Nightly tags can be pruned from Docker Hub over time. For a durable setup, mirror this image to your own Artifact Registry and reference that instead.

## Model access via gcsfuse

The RayCluster (`ray-cluster.train-qwen3-v6e.yaml`) **gcsfuse-mounts the data
bucket at `/data`** on head + worker (`gke-gcsfuse/volumes: "true"` annotation +
a CSI volume). So the Qwen3-4B safetensors, staged to
`gs://BUCKET_NAME/models/qwen3-4b-2507`, appear at `/data/models/qwen3-4b-2507` and
the trainer reads them as a local path. (Tunix's loader also accepts `gs://`
directly if you prefer not to mount.)

```bash
export KSA_NAME=ray-tpu-sa
export TRAIN_IMAGE=REGION-docker.pkg.dev/PROJECT_ID/ray-tpu/ray-tpu-train:v1
export DATA_BUCKET=PROJECT_ID-ray-tpu-data

envsubst < ray-cluster.train-qwen3-v6e.yaml | kubectl apply -f -
```

## Run the DPO job

```bash
kubectl port-forward svc/qwen3-dpo-head-svc 8265:8265 &

ray job submit --address http://localhost:8265 --working-dir . -- \
  python train_dpo_qwen3.py \
    --data /data/ufb-dpo \
    --model-dir /data/models/qwen3-4b-2507 \
    --ckpt-dir /data/ckpts/qwen3-dpo \
    --max-steps 100
```

### What you should see

`JaxTrainer` starts one worker on the slice, the DPO trainer loads the policy +
reference model, applies LoRA, and logs the DPO loss decreasing over steps. The
LoRA checkpoint lands under `/data/ckpts/qwen3-dpo` (i.e. in your bucket).

The slice defaults to a single-host `2x4`. For a multi-host topology, pass
`--topology` and `--num-workers` (one worker per host) to match, and set the
RayCluster's `numOfHosts` to the same count.

## Optional: Weights & Biases tracking

W&B logging is off by default. To enable it:

1. **Store your key in Secret Manager** via Terraform. Set `wandb_api_key` in
   `terraform.tfvars` (the cluster config creates the Secret Manager secret, grants
   the workload SA accessor, and mirrors it to a k8s secret `wandb-api-key`).
2. The RayCluster exposes it as `WANDB_API_KEY` on the workers (via `secretKeyRef`
   with `optional: true`, so pods still start when W&B isn't configured).
3. Pass `--wandb-project` to the job:

   ```bash
   ray job submit --address http://localhost:8265 --working-dir . -- \
     python train_dpo_qwen3.py \
       --data /data/ufb-dpo --model-dir /data/models/qwen3-4b-2507 \
       --ckpt-dir /data/ckpts/qwen3-dpo --max-steps 100 \
       --wandb-project my-qwen3-dpo
   ```

The trainer wires W&B through Tunix's `MetricsLoggerOptions(backend_kwargs={"wandb":
{...}})` on `DPOTrainingConfig`. Without `--wandb-project` there are no external
calls. The training image includes the `wandb` package.

## Next

- **[cluster/monitoring](../cluster/#monitoring)**. Watch TPU utilization + the training run in Grafana.
- **[serve](../serve/)**. Serve the base or fine-tuned model.
