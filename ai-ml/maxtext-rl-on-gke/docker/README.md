# MaxText Post-Training RL / GRPO on Google Cloud TPU (v7x / v6e / v5p)

This repository provides the production Docker container recipe, compatibility patches, and operational recipe for running **MaxText Group Relative Policy Optimization (GRPO)** with **vLLM Rollout Sampling** on Google Cloud TPUs.

---

## 1. Quick Start: Build the Production Container

> **Note for Users**: This container build is **completely standalone** and builds directly from public sources (`python:3.12-slim-bookworm` with GCC 12.2 C++20 toolchain and the official public [Google MaxText GitHub repository](https://github.com/google/maxtext)). It requires **zero access** to any internal or restricted repositories.

All dependencies, Triton uninstallation, PyTorch 2.6 schema fixes, Protobuf collision mocks, and TPU v7 Pallas Ragged Paged Attention (RPA) VMEM tile adjustments are executed automatically during the build:
- `Dockerfile`: Standalone container recipe (clones public MaxText if building from scratch).
- `install_deps.py`: Git clone dependency installer & TPU adapter configurator.
- `patch_tpu_v7.py`: TPU v7 VMEM reduction (`64.2 MB -> ~18 MB`), Protobuf mock, and PyTorch typing patches.

### Option A: Using Google Cloud Build (Recommended)
Run the following commands inside this directory (`ai-ml/maxtext-rl-on-gke/docker/`):
```bash
# 1. Configure your GCP project and Artifact Registry details
export PROJECT_ID="YOUR_GCP_PROJECT_ID"
export REGION="us-east5"
export REPO_NAME="YOUR_ARTIFACT_REGISTRY_REPO"
export IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/maxtext-grpo-runner:v2"

# 2. Submit the build to Google Cloud Build (e2-highcpu-8 accelerates compilation)
gcloud builds submit . \
  --tag="${IMAGE_TAG}" \
  --machine-type="e2-highcpu-8" \
  --project="${PROJECT_ID}" \
  --region="${REGION}"
```

### Option B: Using Standard Docker / Podman (Without Google Cloud Build)

If you do not have Google Cloud Build enabled in your GCP project, you can build and push using standard local **Docker** or **Podman**:

#### 1. Authenticate Docker with Google Artifact Registry
Choose one of the following authentication methods:

```bash
# Method A: Using gcloud credential helper (recommended)
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Method B: Using an active OAuth2 access token
gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://${REGION}-docker.pkg.dev

# Method C: Using a Service Account JSON key
cat /path/to/keyfile.json | docker login -u _json_key --password-stdin https://${REGION}-docker.pkg.dev
```

#### 2. Build and Push the Container
```bash
# Build the image locally
docker build -t ${IMAGE_TAG} .

# Push to your Artifact Registry
docker push ${IMAGE_TAG}
```

*(If using Podman, replace `docker` with `podman`).*

### Option C: Fast Build from an Existing MaxText Runner Image (Optional)
If your organization already maintains a base MaxText runner image, you can pass `--build-arg BASEIMAGE=...` to skip the initial setup step:

```bash
# 1. Define your base image variable
export BASE_IMAGE="YOUR_EXISTING_MAXTEXT_IMAGE"

# 2. Build via Cloud Build:
gcloud builds submit . \
  --tag="${IMAGE_TAG}" \
  --build-arg BASEIMAGE="${BASE_IMAGE}" \
  --machine-type="e2-highcpu-8" \
  --project="${PROJECT_ID}" \
  --region="${REGION}"

# Or build via Local Docker:
docker build --build-arg BASEIMAGE="${BASE_IMAGE}" -t ${IMAGE_TAG} .
docker push ${IMAGE_TAG}
```

---

## 2. LLaMA 3.1-8B GRPO Recipe & Device Topology

In MaxText RL/GRPO, a single TPU slice (e.g. `2x2x1` topology with 1 VM, 4 TPU chips / 8 Tensor Core devices) is partitioned into two concurrent engines:

```
+-------------------------------------------------------------------------------+
|                     Single TPU Slice 2x2x1 (8 TPU Devices)                    |
+---------------------------------------+---------------------------------------+
|        MaxText Policy Trainer         |         vLLM Rollout Sampler          |
|    (4 Devices: TPU_0, 1, 2, 3)        |     (4 Devices: TPU_4, 5, 6, 7)       |
+---------------------------------------+---------------------------------------+
| - Loss: GRPO Policy Gradient + KL     | - Engine: vLLM (flax_nnx backend)     |
| - Optimizer: AdamW                    | - Attention: Pallas RPA Kernel        |
| - Sharding: Data-Parallel (data=4)    | - Sharding: DP Sampling (data=4)      |
| - Computes Reference Log-Probs        | - Generates rollout completions       |
+---------------------------------------+---------------------------------------+
```

### Key Recipe Parameters (`maxtext/configs/post_train/rl.yml`)
* **Model**: `meta-llama/Llama-3.1-8B-Instruct` ($N = 8.030 \times 10^9$ params)
* **Dataset**: `openai/gsm8k` (7,473 grade school math prompts)
* **Rollout Group Size (`num_generations`)**: `2` (default test) or `8` (production)
* **GRPO KL Penalty (`grpo_beta`)**: `0.08`
* **Sequence Length (`max_target_length`)**: `1024`
* **Reward Functions**:
  1. `match_format_exactly`: Enforces `<reasoning>...</reasoning><answer>...</answer>` tags.
  2. `check_numbers`: Compares numerical values inside `<answer>` against GSM8K ground truth.

---

## 3. Production Kubernetes JobSet Manifest

> **Note**: Replace placeholders (such as `<YOUR_REGION>`, `<YOUR_PROJECT_ID>`, `<YOUR_REPO_NAME>`, and `<YOUR_CHECKPOINT_PVC_NAME>`) with your specific cluster and Artifact Registry values before deploying. The key image will have the container that we have built in previous step.

```yaml
apiVersion: jobset.x-k8s.io/v1alpha2
kind: JobSet
metadata:
  name: llama3-1-8b-grpo-spot-2x2x1-training
  namespace: default
  annotations:
    alpha.jobset.sigs.k8s.io/exclusive-topology: cloud.google.com/gke-nodepool
spec:
  failurePolicy:
    maxRestarts: 0
  replicatedJobs:
  - name: slice
    template:
      metadata:
        labels:
          app: llama3-1-8b-grpo-training
      spec:
        parallelism: 1
        completions: 1
        backoffLimit: 0
        template:
          metadata:
            labels:
              app: llama3-1-8b-grpo-training
            annotations:
              gke-gcsfuse/volumes: 'true'
          spec:
            restartPolicy: Never
            securityContext:
              runAsUser: 0
              runAsGroup: 100
              fsGroup: 100
            serviceAccountName: workload-identity-k8s-sa
            automountServiceAccountToken: true
            nodeSelector:
              cloud.google.com/gke-accelerator-count: '4'
              cloud.google.com/gke-nodepool: <USER_NODEPOOL_NAME>
              cloud.google.com/gke-tpu-accelerator: tpu7x
              cloud.google.com/gke-tpu-topology: 2x2x1
              cloud.google.com/gke-spot: 'true'
            tolerations:
            - key: google.com/tpu
              operator: Exists
              effect: NoSchedule
            containers:
            - name: lora-trainer
              image: <YOUR_REGION>-docker.pkg.dev/<YOUR_PROJECT_ID>/<YOUR_REPO_NAME>/maxtext-grpo-runner:v2
              securityContext:
                privileged: true
                runAsUser: 0
                runAsGroup: 100
              env:
              - name: HF_TOKEN
                valueFrom:
                  secretKeyRef:
                    name: hf-secret
                    key: hf_api_token
              - name: VLLM_TARGET_DEVICE
                value: "tpu"
              - name: PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION
                value: "python"
              - name: VLLM_NO_USAGE_STATS
                value: "1"
              - name: TF_CPP_MIN_LOG_LEVEL
                value: "2"
              command:
              - python3
              - -m
              - maxtext.trainers.post_train.rl.train_rl
              - maxtext/configs/post_train/rl.yml
              - model_name=llama3.1-8b-Instruct
              - tokenizer_path=meta-llama/Llama-3.1-8B-Instruct
              - run_name=llama3-1-8b-grpo-run
              - base_output_directory=/checkpoint/maxtext
              - chips_per_vm=4
              resources:
                limits:
                  google.com/tpu: '4'
              volumeMounts:
              - mountPath: /dev/shm
                name: dshm
              - mountPath: /checkpoint
                name: gcs-input
            volumes:
            - name: dshm
              emptyDir:
                medium: Memory
            - name: gcs-input
              persistentVolumeClaim:
                claimName: <YOUR_CHECKPOINT_PVC_NAME>
```

---

## 4. Baseline RL Metrics & Performance Report

### A. Reinforcement Learning Performance Summary
*(Note: The performance below is only for reference with some sample configs set to understand what scores are outputted as part of maxtext default settings. This can be updated later further with more advanced settings to get better performance.)*

From 24 evaluated rollout completions across RL iterations on TPU v7x:

| Metric | Measured Baseline | Notes |
| :--- | :--- | :--- |
| **Mean Reward Score** | **`0.6250`** (62.5%) | Average reward across sampled rollouts |
| **Exact Match Accuracy** | **`62.5%`** (15 / 24) | GSM8K ground truth exact numerical match |
| **XML Format Compliance** | **`70.8%`** (17 / 24) | Valid `<reasoning>...</reasoning><answer>...</answer>` |
| **Post-RL Eval Accuracy** | **`40.0% – 60.0%`** | Held-out 5-question evaluation pass |
| **Post-RL Mean Reward** | **`0.4600 – 0.6800`** | Verification score on test set |

### B. Running the MFU Calculator (Post-Training)
Users can run `calculate_mfu.py` **after training finishes** to evaluate their hardware efficiency based on the measured step time from their run logs:

```bash
# 1. Run with default measured benchmark baseline
python3 calculate_mfu.py

# 2. Or pass custom parameters from your training logs
python3 calculate_mfu.py \
  --params-b 8.03 \
  --chips 4 \
  --batch-size 8 \
  --num-generations 8 \
  --seq-len 1024 \
  --step-time 4.2
```

### C. Sample Rollout Execution Trace
```text
Question: Maria has 4 dimes, 4 quarters, and 7 nickels in her piggy bank. Her mom gives her 5 quarters. How much money, in dollars, does Maria have now?
Ground Truth: 3

Response:
<reasoning>
Initial amount:
4 dimes = 4 * 0.10 = 0.40
4 quarters = 4 * 0.25 = 1.00
7 nickels = 7 * 0.05 = 0.35
Total initial = 0.40 + 1.00 + 0.35 = 1.75 dollars.

Mom gives 5 quarters = 5 * 0.25 = 1.25 dollars.
Total amount = 1.75 + 1.25 = 3.00 dollars.
</reasoning>
<answer> 3.00 </answer>

Extracted: 3.00 | Reward: 1.0 | Format: Valid
```

---

## 5. Built-in Technical Fixes (Executed Automatically at Build Time)

> **User Notice**: You do **NOT** need to run any patch scripts manually. `patch_tpu_v7.py` and `install_deps.py` are automatically executed as intermediate build steps inside the `Dockerfile`.

1. **TPU v7 VMEM SRAM Overflow Fix**:
   - `tpu_inference` RPA kernel hardcoded tile sizes demanding 64.21 MB (exceeding TPU v7's 64.00 MB core SRAM limit).
   - Patched to `bq_sz=128`, `bkv_sz=512`, reducing VMEM usage to ~18 MB.
2. **Protobuf C++ Native Collision (`SIGABRT / Exit -6`)**:
   - Mocks `tpu_info` with pure-Python metadata lookups, avoiding duplicate Protobuf descriptor registrations.
3. **PyTorch 2.6 / Python 3.12 Generics Compatibility**:
   - Automatically translates `list[int]` and `str | None` annotations in custom-ops to `typing.List` and `typing.Optional`.
4. **GPU Triton Removal**:
   - Strips CUDA-only `triton` packages to prevent TPU hardware memory access faults.
