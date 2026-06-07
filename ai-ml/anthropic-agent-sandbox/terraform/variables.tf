# Copyright 2026 Google LLC
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
  description = "Google Cloud project ID."
}

variable "region" {
  type        = string
  description = "Google Cloud region for the Autopilot cluster and Artifact Registry."
  default     = "us-central1"
}

variable "cluster_name" {
  type    = string
  default = "anthropic-agent-sandbox"
}

variable "gke_min_version" {
  type        = string
  description = "Minimum GKE control-plane version. Agent Sandbox add-on requires >= 1.35.2-gke.1269000."
  default     = "1.35.2-gke.1269000"
}

variable "k8s_namespace" {
  type        = string
  description = "Namespace for SandboxTemplate / dispatcher / stats-adapter (created by deploy/, not here)."
  default     = "agent-sandbox"
}

variable "session_output_retention_days" {
  type        = number
  description = "Delete objects in the session-outputs bucket after this many days."
  default     = 7
}

variable "anthropic_environment_key" {
  type        = string
  description = "Anthropic environment key (sk-ant-oat01-...). Stored in Secret Manager; mounted into dispatcher + sandbox pods."
  sensitive   = true
}

variable "anthropic_api_key" {
  type        = string
  description = "Anthropic organization API key. Used ONLY by stats-adapter to read work.stats. Never reaches a sandbox pod."
  sensitive   = true
}
