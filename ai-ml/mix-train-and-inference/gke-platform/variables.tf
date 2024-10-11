# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_id" {
  type        = string
  description = "GCP project id"
  default     = "<your project>"
}

variable "region" {
  type        = string
  description = "GCP project region or zone"
  default     = "us-central1"
}


variable "cluster_name" {
  type        = string
  description = "GKE cluster name"
  default     = "llm-cluster"
}


variable "cluster_labels" {
  type        = map(any)
  description = "GKE cluster labels"
  default = {
    created-by = "ai-on-gke"
  }
}

variable "enable_autopilot" {
  type        = bool
  description = "Set to true to enable GKE Autopilot clusters"
  default     = false
}

variable "gpu_pool_machine_type" {
  type        = string
  description = "Specify the gpu-pool machine type"
  default     = "n1-standard-4"
}

variable "gpu_pool_accelerator_type" {
  type        = string
  description = "Specify the gpu accelerator type"
  default     = "nvidia-tesla-t4"
}

variable "gpu_pool_node_locations" {
  type        = list(any)
  description = "Specify the gpu-pool node zone locations"
  default     = ["us-central1-a", "us-central1-c", "us-central1-f"]
}

variable "enable_fleet" {
  type    = bool
  default = false
}

variable "fleet_project_id" {
  type    = string
  default = ""
}

variable "gateway_api_channel" {
  type        = string
  description = "The gateway api channel of this cluster. Accepted values are `CHANNEL_STANDARD` and `CHANNEL_DISABLED`."
  default     = null
}

variable "gpu_driver_version" {
  type        = string
  description = "the NVIDIA driver version to install"
  default     = "DEFAULT"
}

variable "train_data_bucket" {
  type        = string
  description = "A bucket, containing training data"
}

variable "model_bucket" {
  type        = string
  description = "A bucket where the fine-tuned model will be stored"
}