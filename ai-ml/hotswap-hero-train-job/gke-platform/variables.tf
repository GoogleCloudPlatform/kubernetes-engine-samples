# Copyright 2025 Google LLC
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

variable "enable_tpu" {
  type        = bool
  description = "Set to true to create TPU node pool"
  default     = false
}

variable "tpu_node_location" {
  type        = set(string)
  description = "Location for tpu nodes"
  default     = []
}

variable "tpu_machine_type" {
  type        = string
  description = "Machine type for TPU node pool in standard GKE cluster."
  default     = ""
}

variable "tpu_topology" {
  type        = string
  description = "Topology for standard GKE cluster TPU node pool"
  default     = "1x1"
}

variable "tpu_node_pools_number" {
  description = "Number of TPU node pools in standard GKE cluster."
  default     = 1
}