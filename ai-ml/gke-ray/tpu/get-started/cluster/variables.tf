# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-east5"
}

variable "zone" {
  description = "GCP zone for the GKE cluster and TPU node pools (must have v6e capacity)"
  type        = string
  default     = "us-east5-b"
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "ray-tpu-get-started"
}

variable "cluster_version" {
  description = "GKE cluster version (>= 1.31.1-gke.1846000 for v6e)"
  type        = string
  default     = "1.35.3-gke.1737000"
}

variable "network" {
  description = "VPC network name"
  type        = string
  default     = "default"
}

variable "subnetwork" {
  description = "VPC subnetwork name"
  type        = string
  default     = "default"
}

# TPU configuration. Defaults to a v6e 2x4 slice (8 chips on a single host).
# Qwen3-4B is small and text-only, so one 8-chip v6e host (256 GB HBM) serves it,
# fine-tunes it with LoRA, and runs batch inference. The serve and train
# manifests select tpu-v6e-slice and 2x4, so keep these aligned if you change them.
variable "tpu_machine_type" {
  description = "TPU machine type (ct6e-standard-8t = 8 v6e chips on a single host)"
  type        = string
  default     = "ct6e-standard-8t"
}

variable "tpu_accelerator" {
  description = "GKE TPU accelerator label (cloud.google.com/gke-tpu-accelerator)"
  type        = string
  default     = "tpu-v6e-slice"
}

variable "tpu_topology" {
  description = "TPU topology per slice (2x4 = 8 v6e chips on one host)"
  type        = string
  default     = "2x4"
}

variable "num_tpu_slices" {
  description = "Number of TPU slices (node pools). 1 is enough for the get-started samples."
  type        = number
  default     = 1
}

variable "nodes_per_slice" {
  description = "Number of VMs per TPU node pool (1 for a single-host v6e 2x4 slice)"
  type        = number
  default     = 1
}

variable "tpu_reservation" {
  description = "TPU reservation name. Leave empty to use on-demand or spot."
  type        = string
  default     = ""
}

variable "tpu_spot" {
  description = "Provision TPU node pools as Spot VMs (mutually exclusive with tpu_reservation)."
  type        = bool
  default     = true
}

# CPU node pool. Ray head and Serve controller
variable "cpu_machine_type" {
  description = "Machine type for the Ray head CPU node pool"
  type        = string
  default     = "e2-standard-16"
}

variable "num_cpu_nodes" {
  description = "Number of CPU nodes"
  type        = number
  default     = 1
}

variable "ksa_name" {
  description = "Kubernetes ServiceAccount name (bound to the workload GSA via Workload Identity)"
  type        = string
  default     = "ray-tpu-sa"
}

variable "data_bucket_name" {
  description = "GCS bucket for prepared datasets and checkpoints. Defaults to PROJECT_ID-ray-tpu-data when empty."
  type        = string
  default     = ""
}

variable "hf_token" {
  description = "HuggingFace API token. Optional, since Qwen3-4B and ultrafeedback are ungated. Set only if you also pull a gated model."
  type        = string
  sensitive   = true
  default     = ""
}

variable "wandb_api_key" {
  description = "Weights and Biases API key. Optional, set only to enable WandB logging in the training sample. Stored in Secret Manager and a k8s secret."
  type        = string
  sensitive   = true
  default     = ""
}
