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

1. **[cluster](cluster/)**. Use Terraform to create GKE + Ray Operator add-on + TPU v6e slice + Prometheus/Grafana
2. **[serve](serve/)**. Serve Qwen3-4B on a TPU slice with Ray Serve + vLLM
3. **[data](data/)**. Prepare a DPO dataset
4. **[train](train/)**. DPO fine-tune Qwen3-4B on a TPU slice with Ray Train (JaxTrainer)

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
