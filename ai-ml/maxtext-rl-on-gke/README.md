# MaxText Post-Training RL / GRPO on TPU v7x

This directory contains the production, tested, and verified Kubernetes JobSet manifest for running **Group Relative Policy Optimization (GRPO)** with **vLLM Rollout Sampling** on Google Cloud TPU v7x (`tpu-v7x-spot-2x2x1`).

---

## Verified Manifests

### Option A: **Direct Spot Workload (`2x2x1` Topology)**
* **Manifest File**: [`llama3.1-8b-grpo-spot-2x2x1-training.yaml`](llama3.1-8b-grpo-spot-2x2x1-training.yaml)
* **Target Hardware**: `tpu-v7x-spot-2x2x1` (1 VM with 4 TPU chips / 8 Tensor Core devices)
  * **4 Trainer Devices (`TPU_0` to `TPU_3`)**: MaxText Actor Policy gradient optimizer (AdamW) + reference model log-probability computation.
  * **4 Sampler Devices (`TPU_4` to `TPU_7`)**: vLLM online inference with Pallas Ragged Paged Attention (RPA).
* **Dataset**: `openai/gsm8k`
* **Status**: Tested & Verified (`Succeeded`)

#### How to Run (Direct Spot):
> **Note**: Replace placeholders (such as image URI and PVC claim name) in `llama3.1-8b-grpo-spot-2x2x1-training.yaml` before running.

```bash
kubectl apply -f llama3.1-8b-grpo-spot-2x2x1-training.yaml
```

---

### Option B: **DWS-Flex & Kueue Orchestration (`2x2x1` Topology)**
* **Kueue Setup File**: [`kueue-tpu7x-2x2x1-setup.yaml`](kueue-tpu7x-2x2x1-setup.yaml)
* **JobSet Manifest File**: [`llama3.1-8b-grpo-dws-2x2x1-training.yaml`](llama3.1-8b-grpo-dws-2x2x1-training.yaml)

#### 1. Create the DWS-Flex 2x2x1 Node Pool (Tested & Verified)
Set your environment variables and create the node pool:
```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export CLUSTER_NAME="YOUR_CLUSTER_NAME"
export NODEPOOL_NAME="tpu-v7x-dws-2x2x1"
export REGION="us-central1"
export ZONE="us-central1-a"

gcloud container node-pools create ${NODEPOOL_NAME} \
  --cluster=${CLUSTER_NAME} \
  --location=${REGION} \
  --node-locations=${ZONE} \
  --machine-type="tpu7x-standard-4t" \
  --flex-start \
  --reservation-affinity=none \
  --enable-autoscaling \
  --num-nodes=0 \
  --min-nodes=0 \
  --max-nodes=1 \
  --disk-type="hyperdisk-balanced" \
  --scopes="https://www.googleapis.com/auth/cloud-platform" \
  --project=${PROJECT_ID}
```

#### 2. Apply the Kueue Configuration
Update `<USER_NODEPOOL_NAME>` in `kueue-tpu7x-2x2x1-setup.yaml` and apply:
```bash
kubectl apply -f kueue-tpu7x-2x2x1-setup.yaml
```

#### 3. Submit the GRPO JobSet to Kueue
Update image and volume placeholders in `llama3.1-8b-grpo-dws-2x2x1-training.yaml` and submit:
```bash
kubectl apply -f llama3.1-8b-grpo-dws-2x2x1-training.yaml
```

#### 4. Monitor Provisioning & Execution
```bash
# Check Kueue Workload admission status
kubectl get workloads

# Watch DWS Provisioning Request (ACCEPTED -> PROVISIONED)
kubectl get provisioningrequests -w

# Watch TPU node scaling from 0 to 1
kubectl get nodes -w

# Stream GRPO training logs
kubectl logs -l app=llama3-1-8b-grpo-training -c grpo-trainer -f
```

---

## Container Build Quickstart

Set your environment variables before building the container:
```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="us-central1"
export REPO_NAME="YOUR_ARTIFACT_REGISTRY_REPO"
export IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/maxtext-grpo-runner:v2"
```

You can build the container using either **Google Cloud Build** or local **Docker / Podman**:

### Option 1: Using Google Cloud Build
```bash
cd docker
gcloud builds submit . \
  --tag="${IMAGE_TAG}" \
  --machine-type="e2-highcpu-8" \
  --project="${PROJECT_ID}" \
  --region="${REGION}"
```

### Option 2: Using Local Docker (Without Cloud Build)
```bash
cd docker

# 1. Authenticate Docker with Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# 2. Build and push
docker build -t ${IMAGE_TAG} .
docker push ${IMAGE_TAG}
```

---

## Detailed Documentation
* **Architecture & Topology**: [`docker/README.md`](docker/README.md)
* **Custom Dataset & Reward Functions Guide**: [`CUSTOM_DATASET_AND_REWARDS_GUIDE.md`](CUSTOM_DATASET_AND_REWARDS_GUIDE.md)
* **TRL to MaxText Mapping**: [`TRL_TO_MAXTEXT_MAPPING.md`](TRL_TO_MAXTEXT_MAPPING.md)
* **Custom Reward Functions Template**: [`custom_rewards_template.py`](custom_rewards_template.py)
* **Kueue 2x2x1 Setup Manifest**: [`kueue-tpu7x-2x2x1-setup.yaml`](kueue-tpu7x-2x2x1-setup.yaml)
* **DWS 2x2x1 JobSet Manifest**: [`llama3.1-8b-grpo-dws-2x2x1-training.yaml`](llama3.1-8b-grpo-dws-2x2x1-training.yaml)
* **MFU Performance Calculator**: [`docker/calculate_mfu.py`](docker/calculate_mfu.py)
