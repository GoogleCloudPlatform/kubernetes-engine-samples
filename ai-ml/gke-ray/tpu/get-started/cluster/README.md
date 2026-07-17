# Provision the Ray on TPU cluster on GKE

Terraform that stands up everything the get-started samples need:

- A **GKE** cluster with the **Ray Operator add-on** (installs KubeRay + the Ray
  TPU webhook) and the GCS FUSE CSI driver.
- A **CPU** node pool for the Ray head, and a **TPU v6e** slice (default `2x4` =
  8 chips on a single `ct6e-standard-8t` host, Spot).
- **Workload Identity**: a GCP service account bound to a Kubernetes
  ServiceAccount (`ray-tpu-sa`).
- **kube-prometheus-stack** (Prometheus + Grafana) plus the Ray Grafana
  dashboards, so metrics work out of the box (see [Monitoring](#monitoring)).
- Optional **Secret Manager** entry for a Hugging Face token (only created if you
  set one, and since Qwen3-4B and ultrafeedback are ungated, you can skip it).

## Why v6e 2x4

A single v6e host is a `2x4` slice, 8 chips with 256 GB of HBM. One slice can
serve Qwen3-4B, fine-tune it with LoRA, and run batch inference. The whole
get-started set (serve, data, train) targets this
slice, so the serve and train manifests select `tpu-v6e-slice` / `2x4`.

## Prerequisites

Before you provision the cluster, make sure you have:

- `terraform` >= 1.5, `gcloud`, `kubectl`.
- A GCP project with **TPU v6e quota** in your chosen zone. Check with:
  ```bash
  gcloud compute regions describe REGION \
    --format="value(quotas)" | tr ',' '\n' | grep -i tpu
  ```
- Authenticated: `gcloud auth application-default login`.

## Provision

```bash
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: set project_id and zone (must have v6e capacity)

terraform init
terraform apply
```

Then wire up `kubectl`:

```bash
gcloud container clusters get-credentials "$(terraform output -raw cluster_name)" \
  --location "$(terraform output -raw cluster_zone)"
```

You should see the head/worker pools come up and the KubeRay operator running.

## What you get (outputs)

```bash
terraform output
# cluster_name, cluster_zone, tpu_node_pools, k8s_service_account,
# workload_service_account, data_bucket, hf_secret_name (empty unless a token was set)
```

Use `k8s_service_account` as `KSA_NAME` in the other samples.

## Monitoring

Prometheus, Grafana, and Ray's Grafana dashboards are installed with the cluster.
One manual step tells Prometheus to scrape Ray's metrics:

```bash
kubectl apply -f monitoring/podmonitor.yaml
```

Then watch a run:

- **Ray Dashboard** shows live TPU utilization and HBM, plus a Serve tab while
  serving:
  ```bash
  kubectl port-forward svc/RAY_CLUSTER_NAME-head-svc 8265:8265
  # open http://localhost:8265
  ```
- **Grafana** has the `ray-default`, `ray-serve`, `ray-data`, and `ray-train`
  dashboards:
  ```bash
  kubectl -n prometheus-system port-forward svc/prometheus-stack-grafana 3000:80
  # open http://localhost:3000  (default login admin / prom-operator)
  ```

## Cost & cleanup

The TPU slice is the cost driver. It's **Spot** by default (cheaper, can be
preempted). **Tear it down when you're done:**

```bash
terraform destroy
```

## Next

- [serve](../serve/) runs Qwen3-4B on the slice with Ray Serve + vLLM.
- [data](../data/) · [train](../train/)
