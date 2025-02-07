# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

variable "project_id" {
  description = "The project ID to host the cluster in"
  default     = ""
  type        = string
}

variable "region" {
  description = "The region to host the cluster in"
  type        = string
}

variable "cluster_prefix" {
  description = "The prefix for all cluster resources"
  default     = "elasticsearch"
  type        = string
}

variable "node_machine_type" {
  description = "The machine type for node instances"
  default     = "e2-standard-2"
  type        = string
}

variable "node_disk_type" {
  description = "The persistent disk type for node instances"
  default     = "pd-standard"
  type        = string
}

variable "node_disk_size" {
  description = "The persistent disk size for node instances"
  default     = 20
  type        = number
}

variable "autoscaling_max_count" {
  description = "Maximum node counts per zone"
  default     = 2
  type        = number
}

