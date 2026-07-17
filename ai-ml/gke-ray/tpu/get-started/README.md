# Get started with Ray on TPU with GKE

Runnable, get-started samples for running Ray on TPU with GKE. Each one is a
small, self-contained on-ramp for a single Ray library on Cloud TPU, using
[`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
(a small, text-only LLM, Apache-2.0) and the
[`HuggingFaceH4/ultrafeedback_binarized`](https://huggingface.co/datasets/HuggingFaceH4/ultrafeedback_binarized)
preference dataset (MIT). Both are ungated.

## Content

The repository is organized in a way to cover the entire end-to-end lifecycle of [`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), from cluster creation, data preparation, tuning and serving.

Here's how to approach its content:

1. Use Terraform in **[cluster](cluster/)** to create the whole environment, including a GKE cluster with the Ray Operator add-on, a single-host TPU v6e `2x4` slice (8 chips), and a Prometheus + Grafana monitoring stack.
2. Serve Qwen3-4B in **[serve](serve/)** with Ray Serve and vLLM, using topology-aware scheduling to reserve the whole slice and run tensor parallelism across all 8 chips.
3. Use Ray Data in **[data](data/)** to prepare a DPO preference dataset and run offline batch prediction across the slice's chips.
4. Run a DPO fine-tune of Qwen3-4B in **[train](train/)** on the slice with Ray Train's JaxTrainer and Tunix, using qwix LoRA and checkpointing to Cloud Storage.

In **[data](data/)**, you also have a sample for batch-prediction on the slice with Ray Data.

Start with **cluster**. The other three run against the cluster it creates.

> [!NOTE]
> `cluster/` is self-contained, so this tutorial runs with a single
> `terraform apply` and does not depend on the repo's shared `gke-platform`
> module.

## Monitoring

Prometheus, Grafana, and Ray's Grafana dashboards come with the
[cluster](cluster/). Apply the PodMonitor and open the Ray Dashboard or Grafana.
See [cluster/monitoring](cluster/#monitoring).

## Hardware

The samples run on a single **TPU v6e** host: a `2x4` slice (8 chips,
`ct6e-standard-8t`), provisioned by [cluster](cluster/). Qwen3-4B is small and
text-only, so one 8-chip host has ample HBM (256 GB) to serve it, fine-tune it
with LoRA, and run batch inference.

## Cost

TPU is the cost driver, and the slice is **Spot** by default. Run
`terraform destroy` in [cluster](cluster/) when you're done.
