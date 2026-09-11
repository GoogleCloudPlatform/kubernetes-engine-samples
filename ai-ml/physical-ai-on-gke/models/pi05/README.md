# Physical Intelligence PI0.5 (3.4B VLA) on GKE

This directory contains the production Kubernetes manifests, Ray distributed scripts, and simulation tools for running **Physical Intelligence PI0.5** on Google Kubernetes Engine (GKE).

---

## Architecture Overview

* **Model Architecture**: 3.4B parameter Vision-Language-Action (VLA) foundation model consisting of a frozen PaliGemma vision-language backbone and 27.27M trainable action expert projection MLP heads predicting 50-step action chunks.
* **Hardware Target**: 8 $\times$ NVIDIA RTX 6000 Ada GPUs on a single `g4-standard-384` GKE node.
* **Storage Mount**: Cloud Storage FUSE CSI driver mounting `gs://checkpoint-data-...` at `/checkpoint`.

---

## Directory Structure

```
models/pi05/
├── manifests/
│   ├── 00-configmaps.yaml              # Auto-generated ConfigMaps for tools and scripts
│   ├── 00-mirror-sync-job.yaml         # One-time dataset & model mirror job
│   ├── 01-data-processing-rayjob.yaml  # Phase 1: Ray Data streaming pipeline
│   ├── 02-vla-training-rayjob.yaml     # Phase 2: 1,000-step 8-GPU DDP fine-tuning
│   ├── 02b-generate-demos-job.yaml     # Phase 2b: Demonstration trajectory generation
│   ├── 03-serving-sim-eval-rayjob.yaml # Phase 3: Ray Serve + 8-GPU simulation eval flywheel
│   └── 03b-vla-serving-rayservice.yaml # Phase 3b: Persistent 24/7 Kubernetes RayService
├── scripts/
│   ├── 01_robotics_data_pipelines.py   # Distributed LeRobot data reader & preprocessor
│   ├── 02_vla_finetuning.py            # Ray Train TorchTrainer DDP fine-tuning engine
│   └── 03_serving_and_sim_eval.py      # Ray Serve application & closed-loop sim flywheel
└── tools/
    ├── cluster.py                      # Hardware detection and worker sizing
    ├── franka_env.py                   # Franka Emika Panda physics environment
    ├── generate_franka_demos.py        # Demo generator script
    ├── lerobot_datasource.py           # High-throughput Ray Data LeRobot datasource
    ├── policy_server.py                # FastAPI & Ray Serve PI05 server definition
    ├── setup_vla_deps.sh               # Runtime dependency installer
    ├── sim_worker.py                   # Distributed simulation worker actor
    ├── sync_mirror_from_anyscale.py    # Anyscale public bucket mirror script
    ├── util.py                         # Checkpoint, collation, and staging helpers
    └── viz.py
```

---

## Execution Guide

### 0. Dataset & Model Weight Staging (Optional)

> [!NOTE]
> **Data Sourcing**: The demonstration data and pretrained weights for this experiment provided by Anyscale reside on an S3 bucket, hence we are using the mirror script (`00-mirror-sync-job.yaml`) to clone the data into the cluster's Cloud Storage bucket. If you have custom data, you can directly load it from your GCS bucket without running the mirror sync step.

```bash
# Optional: Stage experiment data from Anyscale public bucket to GCS
kubectl apply -f models/pi05/manifests/00-mirror-sync-job.yaml
```

### 1. Configure Kubernetes ConfigMaps
Sync the Python scripts and tools into Kubernetes ConfigMaps so they are dynamically mounted into Ray pods:

```bash
kubectl create configmap physical-ai-tools --from-file=models/pi05/tools/ --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap physical-ai-scripts --from-file=models/pi05/scripts/ --dry-run=client -o yaml | kubectl apply -f -
```

### 2. Phase 1: Distributed Data Pipeline
Stream 273,465 frames from GCS FUSE:
```bash
kubectl apply -f models/pi05/manifests/01-data-processing-rayjob.yaml
```

### 3. Phase 2: 1,000-Step VLA Training (8 GPUs)
Fine-tune the model with PyTorch DDP across all 8 RTX 6000 Ada GPUs:
```bash
kubectl apply -f models/pi05/manifests/02-vla-training-rayjob.yaml
```

### 4. Phase 2b: Demonstration Generation
Generate 2,500 high-reward demonstration frames for Franka Panda manipulation:
```bash
kubectl apply -f models/pi05/manifests/02b-generate-demos-job.yaml
```

### 5. Phase 3: Serving & 8-Chip Simulation Eval Flywheel
Run Ray Serve on GPU 0 and evaluate 8 parallel Franka simulation workers on GPUs 0–7:
```bash
kubectl apply -f models/pi05/manifests/03-serving-sim-eval-rayjob.yaml
```

### 6. Phase 3b: Persistent Production Serving
Deploy the fine-tuned checkpoint as a 24/7 self-healing RayService:
```bash
kubectl apply -f models/pi05/manifests/03b-vla-serving-rayservice.yaml
```
