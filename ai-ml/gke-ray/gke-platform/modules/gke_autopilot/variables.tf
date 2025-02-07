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
  default     = "ricliu-gke-dev"
}

variable "region" {
  type        = string
  description = "GCP project region or zone"
  default     = "us-central1"
}

variable "cluster_name" {
  type        = string
  description = "GKE cluster name"
  default     = "ml-cluster"
}

variable "cluster_labels" {
  type        = map
  description = "GKE cluster labels"
  default     =  {
    created-by = "ai-on-gke"
  }
}

variable "namespace" {
  type        = string
  description = "Kubernetes namespace where resources are deployed"
  default     = "ray"
}

variable "num_gpu_nodes" {
  description = "Number of GPU nodes in the cluster"
  default     = 1
}

variable "enable_autopilot" {
  type        = bool
  description = "Set to true to enable GKE Autopilot clusters"
  default     = false
}
