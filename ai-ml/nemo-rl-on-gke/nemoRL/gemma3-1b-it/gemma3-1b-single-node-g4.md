This document provides a step-by-step guide on how to run NeMo-RL on a single Google Cloud G4 instance featuring NVIDIA RTX PRO 6000 GPUs. The goal is to showcase the implementation of NeMo-RL for large language model training and inference. For more information on the G4 instances, please refer to the official Google Cloud documentation: [https://docs.cloud.google.com/compute/docs/gpus#rtx-6000-gpus](https://docs.cloud.google.com/compute/docs/gpus#rtx-6000-gpus).

## 1. Exports
These environment variables are used to configure the gcloud commands in the following steps. Make sure to replace the placeholder for `PROJECT` with your Google Cloud project ID.

```bash
export VM_NAME=generic-g4-test
export PROJECT=<your-gcp-project>
export REGION=us-central1
export ZONE=us-central1-f
```

## 2. Create RTX PRO 6000 (G4) VM
This command creates a new Google Compute Engine virtual machine instance with the specified configuration. The machine type is `g4-standard-384` and it is equipped with 8 NVIDIA RTX PRO 6000 GPUs. The boot disk is a 3TB hyperdisk and the image used is a pre-configured Ubuntu image with NVIDIA drivers.

```bash
gcloud compute instances create $VM_NAME \
    --project=$PROJECT \
    --zone=$ZONE \
    --machine-type=g4-standard-384 \
    --network-interface=network-tier=PREMIUM,stack-type=IPV4_ONLY,subnet=default \
    --metadata=enable-osconfig=TRUE,enable-oslogin=true \
    --maintenance-policy=TERMINATE \
    --provisioning-model=STANDARD \
    --service-account=9452062936-compute@developer.gserviceaccount.com \
    --scopes=https://www.googleapis.com/auth/devstorage.read_only,https://www.googleapis.com/auth/logging.write,https://www.googleapis.com/auth/monitoring.write,https://www.googleapis.com/auth/service.management.readonly,https://www.googleapis.com/auth/servicecontrol,https://www.googleapis.com/auth/trace.append \
    --accelerator=count=8,type=nvidia-rtx-pro-6000 \
    --create-disk=auto-delete=yes,boot=yes,device-name=$VM_NAME,disk-resource-policy=projects/$PROJECT/regions/$REGION/resourcePolicies/default-schedule-1,image=projects/ubuntu-os-accelerator-images/global/images/ubuntu-accelerator-2404-amd64-with-nvidia-580-v20260225,mode=rw,provisioned-iops=21000,provisioned-throughput=2400,size=3000,type=hyperdisk-balanced \
    --no-shielded-secure-boot \
    --shielded-vtpm \
    --shielded-integrity-monitoring \
    --reservation-affinity=any
```

## 3. SSH into the newly created VM
This command establishes an SSH connection to the newly created VM, allowing you to execute commands on the remote machine.

```bash
gcloud compute ssh --zone "$ZONE" "$VM_NAME" --project "$PROJECT"
```

## 4. Docker and NVIDIA Container toolkit setup
These commands install Docker and the NVIDIA Container Toolkit on the VM. Docker is used to run containerized applications, and the NVIDIA Container Toolkit allows Docker containers to access the GPUs.

```bash
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo apt-get update && sudo apt-get install -y --no-install-recommends \
   ca-certificates \
   curl \
   gnupg2

curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update

export NVIDIA_CONTAINER_TOOLKIT_VERSION=1.18.2-1
  sudo apt-get install -y \
      nvidia-container-toolkit=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      nvidia-container-toolkit-base=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container-tools=${NVIDIA_CONTAINER_TOOLKIT_VERSION} \
      libnvidia-container1=${NVIDIA_CONTAINER_TOOLKIT_VERSION}


sudo nvidia-ctk runtime configure --runtime=docker

sudo systemctl restart docker

sudo nvidia-ctk config --set nvidia-container-cli.no-cgroups --in-place
```

## 5. Run a nemorl container
This command pulls and runs the NeMo-RL container from the NVIDIA container registry. The `--gpus all` flag makes all GPUs available to the container, and the other flags configure the container's environment.

```bash
sudo docker run --runtime=nvidia --gpus all \
    --net=host \
    --shm-size="10g" \
    --cap-add=SYS_ADMIN \
    --rm -it \
    --entrypoint /bin/bash \
    nvcr.io/nvidia/nemo-rl:v0.5.0
```

## 6. Pre-process the dataset so it works with our GRPO example
These commands modify the NeMo-RL source code to correctly load the `openai/gsm8k` dataset. This is a temporary workaround and may not be necessary in future versions of NeMo-RL.

```bash
sed -i 's/subset: Optional\[str\] = None/subset: Optional[str] = "main"/' /opt/nemo-rl/nemo_rl/data/datasets/response_datasets/response_dataset.py
sed -i 's/raw_dataset = load_dataset(data_path)/raw_dataset = load_dataset(data_path, "main")/' /opt/nemo-rl/nemo_rl/data/datasets/utils.py
```

## 7. Run GRPO for Gemma3-1b
This command starts the GRPO (Generative Reward Policy Optimization) training process for the Gemma3-1b model. The configuration file `grpo-gemma3-1b-it-1n8g-fsdp2tp1.yaml` specifies the model, dataset, and training parameters. We override some of these parameters on the command line to use the `openai/gsm8k` dataset and to limit the training to 10 steps.

```bash
uv run python examples/run_grpo_math.py \
  --config examples/configs/recipes/llm/grpo-gemma3-1b-it-1n8g-fsdp2tp1.yaml \
  cluster.num_nodes=1 \
  cluster.gpus_per_node=8 \
  grpo.max_num_steps=10 \
  data.dataset_name=ResponseDataset \
  +data.train_data_path=openai/gsm8k \
  +data.val_data_path=openai/gsm8k \
  +data.val_split=test \
  +data.train_split=train \
  +data.subset="main" \
  +data.input_key="question" \
  +data.output_key="answer" \
  grpo.num_prompts_per_step=16 \
  grpo.num_generations_per_prompt=64 \
  logger.tensorboard_enabled=False \
  logger.wandb_enabled=False
```

## 8. Results, should look similar to:
The following output shows the training results and performance metrics after the training is complete. The "Training Results" section shows the loss, generation KL error, average reward, and mean generation length. The "Timing" section shows the time spent in different parts of the training process. The "Performance Metrics" section shows the throughput in terms of samples per second and tokens per second.

``` bash
📊 Training Results:
  • Loss: 0.0000
  • Generation KL Error: 0.0010
  • Avg Reward: 0.0000
  • Mean Generation Length: 201.2197

⏱️  Timing:
  • Total step time: 35.70s
  • policy_training: 10.97s (30.7%)
  • checkpointing: 6.49s (18.2%)
  • generation: 4.95s (13.9%)
  • policy_and_reference_logprobs: 3.14s (8.8%)
  • prepare_for_generation/total: 2.20s (6.2%)
  • logprob_inference_prep: 0.85s (2.4%)
  • training_prep: 0.75s (2.1%)
  • prepare_for_generation/transfer_and_update_weights: 0.60s (1.7%)
  • data_processing: 0.09s (0.2%)
  • reward_calculation: 0.01s (0.0%)

🔍 Performance Metrics:
  • Mean Total Tokens per Sample: 204.01
  • Throughputs (per GPU):
    - E2E (Samples/sec/gpu): 3.59
    - E2E (Tokens/sec/gpu): 1073.59
    - Policy Training (Tokens/sec/gpu): 3492.73
    - Policy and Reference Logprobs (Tokens/sec/gpu): 12201.78
    - Training Worker Group (Tokens/sec/gpu): 2715.44
    - Generation Worker Group (Tokens/sec/gpu): 7745.97
  • Throughputs (per Group):
    - E2E (Samples/sec): 28.68
    - E2E (Tokens/sec): 8588.75
    - Training Worker Group (Tokens/sec): 21723.53
    - Generation Worker Group (Tokens/sec): 61967.76
```