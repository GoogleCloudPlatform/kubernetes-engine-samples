# Serve Qwen3-4B on a TPU slice with Ray Serve and vLLM

Deploy
[`Qwen/Qwen3-4B-Instruct-2507`](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
(a small, text-only LLM, Apache-2.0) on a Cloud TPU v6e slice using Ray Serve and
vLLM. One config field, `accelerator_config.topology`, gang-schedules every vLLM
worker onto one TPU slice so they share the high-speed interconnect (ICI).

The sample assumes a GKE cluster with the Ray Operator add-on; see the top-level
get-started README for cluster setup.

## Prerequisites

Before you deploy, make sure you have:

- A GKE cluster with the Ray Operator add-on and a **TPU v6e** node pool
  (`2x4`, single host, 8 chips, `ct6e-standard-8t`). See [`../cluster/`](../cluster/).
- A Kubernetes ServiceAccount (`ray-tpu-sa`) with access to your model cache bucket.
- A serve image built from `Dockerfile` (vLLM-TPU nightly + a `protobuf<6` pin
  that `ray.serve.llm` needs). Build it with `cloudbuild.yaml`:
  ```bash
  gcloud builds submit --config cloudbuild.yaml \
    --substitutions=_IMAGE=REGION-docker.pkg.dev/PROJECT_ID/ray-tpu/serve-qwen-tpu:v1 .
  ```
- `kubectl`, `envsubst`.

> Note:
> Qwen3-4B serves on vLLM-TPU's **JAX-native** (`flax_nnx`) path. It's in the
> architecture registry (`tpu_inference/models/jax/qwen3.py`), so there's no
> torchax fallback. Set `JAX_PLATFORMS=tpu,cpu` (not `tpu` alone): the weight
> loader stages through the CPU backend, so a `tpu`-only value crashes with
> `Unknown backend cpu`.

## About the base image

The image is a pinned nightly, `vllm/vllm-tpu:nightly-20260701-6af3d12-9969466`,
the first to bundle Ray 2.56, vLLM, and `ray.serve.llm` on TPU.

Nightly tags can be pruned from Docker Hub over time. For a durable setup,
mirror this image to your own Artifact Registry and reference that instead.

In the image, the pin locks the validated stack, and `Dockerfile` adds the
`protobuf<6` fix and `haproxy` for the high-throughput ingress with Ray Serve.
You enable high-throughput serving (Ray 2.56+) with env vars on the head and
worker:

- `RAY_SERVE_ENABLE_HA_PROXY` puts an HAProxy load balancer in front of each
  pod's Serve proxy.
- `RAY_SERVE_THROUGHPUT_OPTIMIZED` turns on throughput optimizations, including
  direct gRPC data-plane traffic between Serve replicas.
- `RAY_SERVE_LLM_ENABLE_DIRECT_STREAMING` streams requests and responses
  straight to the backend instead of through the ingress.
- `VLLM_USE_RAY_V2_EXECUTOR_BACKEND` runs vLLM on the Ray V2 executor backend.

These help most under high load with multiple replicas. See the
[KubeRay high-throughput guide](https://docs.ray.io/en/master/cluster/kubernetes/user-guides/kuberay-serve-high-throughput.html).

## Deploy

`serve_qwen3_tpu.py` is mounted into the pods from a ConfigMap. Create it, then
render the manifest (image + service account) and apply it:

```bash
export KSA_NAME=ray-tpu-sa
export SERVE_IMAGE=REGION-docker.pkg.dev/PROJECT_ID/ray-tpu/serve-qwen-tpu:v1

kubectl create configmap qwen3-serve-code --from-file=serve_qwen3_tpu.py
envsubst < ray-service.qwen3-tpu-v6e.yaml | kubectl apply -f -
```

Wait for the service to become ready:

```bash
kubectl get rayservice qwen3-serve -o jsonpath='{.status.serviceStatus}{"\n"}'
# -> Running
```

You should see one head pod and one TPU worker pod; it holds all 8 chips of the slice.

## Send a request

Port-forward the serve endpoint, then use the included `predict.py` (an
OpenAI-client script) or a raw curl.

```bash
kubectl port-forward svc/qwen3-serve-serve-svc 8000:8000 &
```

With the script (`pip install openai` first):

```bash
python predict.py "In one sentence, what is a TPU slice?"
```

Or with curl:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-4B-Instruct-2507",
    "messages": [{"role": "user", "content": "In one sentence, what is a TPU slice?"}]
  }'
```

## Watch it run: Ray Dashboard + Grafana

The cluster ships with the Ray Dashboard and a Grafana stack (from
[`../cluster/`](../cluster/)). While the model serves:

```bash
# Ray Dashboard, Serve tab + Cluster tab (live TPU utilization / HBM)
kubectl port-forward svc/qwen3-serve-head-svc 8265:8265
#   open http://localhost:8265

# Grafana, the Ray "Serve LLM" dashboard is auto-loaded
kubectl -n prometheus-system port-forward svc/prometheus-stack-grafana 3000:80
#   open http://localhost:3000  (default login admin / prom-operator)
```

See [cluster/monitoring](../cluster/#monitoring) for the full metrics walkthrough.

## How it works

Looking at the serving module:

- `serve_qwen3_tpu.py` builds an OpenAI-compatible app with `build_openai_app`.
  The key line is `accelerator_config={"kind": "tpu", "topology": "2x4"}`: with a
  topology set, Ray Serve defers placement to the replica, which reserves a whole
  slice via a `SlicePlacementGroup`. Drop it and a multi-host model can fragment
  across slices and hang in `DEPLOYING`.
- `tensor_parallel_size` (8) equals the chip count of the `2x4` topology.
- The pods run a vLLM-TPU image with one dependency pin (see `Dockerfile`):
  `ray.serve.llm` needs `protobuf<6`, which the base nightly ships too new.

## Clean up

```bash
kubectl delete rayservice qwen3-serve
kubectl delete configmap qwen3-serve-code
```

## Next

- **[data](../data/)**. Prepare a DPO dataset and batch-predict with Ray Data.
- **[train](../train/)**. DPO fine-tune Qwen3-4B on a TPU slice with JaxTrainer.
- **[cluster/monitoring](../cluster/#monitoring)**. TPU metrics in the Ray Dashboard and Grafana.
