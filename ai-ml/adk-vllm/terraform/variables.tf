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
}

variable "cluster_name" {
  type = string
}

variable "cluster_location" {
  type = string
}

variable "cluster_membership_id" {
  type        = string
  description = "require to use connectgateway for private clusters, default: cluster_name"
  default     = ""
}

variable "kubernetes_namespace" {
  type        = string
  description = "Kubernetes namespace where resources are deployed"
  default     = "ai-on-gke"
}

variable "create_service_account" {
  type        = bool
  description = "Creates a google IAM service account & k8s service account & configures workload identity"
  default     = true
}

variable "workload_identity_service_account" {
  type        = string
  description = "Google Cloud IAM service account for authenticating with GCP services for GCS"
  default     = "ray-sa"
}

variable "artifact_registry_name" {
  type = string
  description = "Name of Artifact Registry Repository"
  default = "adk-repo"
}

variable "artifact_registry_location" {
  type = string
  description = "Location of Artifact Registry Repository"
  default = "us-central1"
}

variable "enable_gpu" {
  type    = bool
  default = false
}

variable "enable_tpu" {
  type    = bool
  default = false
}

## GKE variables
variable "create_cluster" {
  type    = bool
  default = false
}

variable "private_cluster" {
  type    = bool
  default = false
}

variable "autopilot_cluster" {
  type    = bool
  default = true
}

variable "cpu_pools" {
  type = list(object({
    name                   = string
    machine_type           = string
    node_locations         = optional(string, "")
    autoscaling            = optional(bool, false)
    min_count              = optional(number, 1)
    max_count              = optional(number, 3)
    local_ssd_count        = optional(number, 0)
    spot                   = optional(bool, false)
    disk_size_gb           = optional(number, 100)
    disk_type              = optional(string, "pd-standard")
    image_type             = optional(string, "COS_CONTAINERD")
    enable_gcfs            = optional(bool, false)
    enable_gvnic           = optional(bool, false)
    logging_variant        = optional(string, "DEFAULT")
    auto_repair            = optional(bool, true)
    auto_upgrade           = optional(bool, true)
    create_service_account = optional(bool, true)
    preemptible            = optional(bool, false)
    initial_node_count     = optional(number, 1)
    accelerator_count      = optional(number, 0)
  }))
  default = [{
    name         = "cpu-pool"
    machine_type = "n1-standard-16"
    autoscaling  = true
    min_count    = 1
    max_count    = 3
    enable_gcfs  = true
    disk_size_gb = 100
    disk_type    = "pd-standard"
  }]
}

variable "gpu_pools" {
  type = list(object({
    name                   = string
    machine_type           = string
    node_locations         = optional(string, "")
    autoscaling            = optional(bool, false)
    min_count              = optional(number, 1)
    max_count              = optional(number, 3)
    local_ssd_count        = optional(number, 0)
    spot                   = optional(bool, false)
    disk_size_gb           = optional(number, 100)
    disk_type              = optional(string, "pd-standard")
    image_type             = optional(string, "COS_CONTAINERD")
    enable_gcfs            = optional(bool, false)
    enable_gvnic           = optional(bool, false)
    logging_variant        = optional(string, "DEFAULT")
    auto_repair            = optional(bool, true)
    auto_upgrade           = optional(bool, true)
    create_service_account = optional(bool, true)
    preemptible            = optional(bool, false)
    initial_node_count     = optional(number, 1)
    accelerator_count      = optional(number, 0)
    accelerator_type       = optional(string, "nvidia-tesla-t4")
    gpu_driver_version     = optional(string, "DEFAULT")
    queued_provisioning    = optional(bool, false)
  }))
  default = [{
    name               = "gpu-pool-l4"
    machine_type       = "g2-standard-24"
    autoscaling        = true
    min_count          = 0
    max_count          = 3
    disk_size_gb       = 100
    disk_type          = "pd-balanced"
    enable_gcfs        = true
    accelerator_count  = 2
    accelerator_type   = "nvidia-l4"
    gpu_driver_version = "DEFAULT"
  }]
}

variable "goog_cm_deployment_name" {
  type    = string
  default = ""
}

# Ray-dashboard IAP settings
variable "create_brand" {
  type        = bool
  description = "Create Brand OAuth Screen"
  default     = false
}

variable "ray_dashboard_add_auth" {
  type        = bool
  description = "Enable iap authentication on frontend"
  default     = true
}

variable "ray_dashboard_k8s_ingress_name" {
  type    = string
  default = "ray-dashboard-ingress"
}

variable "ray_dashboard_k8s_managed_cert_name" {
  type        = string
  description = "Name for frontend managed certificate"
  default     = "ray-dashboard-managed-cert"
}

variable "ray_dashboard_k8s_iap_secret_name" {
  type    = string
  default = "ray-dashboard-secret"
}

variable "ray_dashboard_k8s_backend_config_name" {
  type        = string
  description = "Name of the Backend Config on GCP"
  default     = "ray-dashboard-iap-config"
}

variable "ray_dashboard_k8s_backend_service_port" {
  type        = number
  description = "Name of the K8s Backend Service Port"
  default     = 8265
}

variable "ray_dashboard_domain" {
  type        = string
  description = "Domain used for SSL certificate."
  default     = ""
}

variable "support_email" {
  type        = string
  description = "Email for users to contact with questions about their consent"
  default     = "<email>"
}

variable "ray_dashboard_client_id" {
  type        = string
  description = "Client ID used for enabling IAP"
  default     = ""
}

variable "ray_dashboard_client_secret" {
  type        = string
  description = "Client secret used for enabling IAP"
  default     = ""
  sensitive   = false
}

variable "ray_dashboard_members_allowlist" {
  type    = string
  default = ""
  ## keeping it string type to support single field input for marketplace UI.
}

# These default resource quotas are set intentionally high as an example that won't be limiting for most Ray clusters.
# Consult https://kubernetes.io/docs/concepts/policy/resource-quotas/ for additional quotas that may be set.
variable "resource_quotas" {
  description = "Kubernetes ResourceQuota object to attach to the Ray cluster's namespace"
  type        = map(string)
  default = {
    cpu                       = "1000"
    memory                    = "10Ti"
    "requests.nvidia.com/gpu" = "100"
    "requests.google.com/tpu" = "100"
  }
}

variable "disable_resource_quotas" {
  description = "Set to true to remove resource quotas from your Ray clusters. Not recommended"
  type        = bool
  default     = false
}

# This is a list of CIDR ranges allowed to access a Ray cluster's job submission API and Dashboard.
#
# Example:
# kuberay_network_policy_allow_cidr = "10.0.0.0/8"
#
variable "kuberay_network_policy_allow_cidr" {
  description = "List of CIDRs that are allowed to access this Ray cluster's job submission and dashboard port."
  type        = string
  default     = ""
}

variable "disable_ray_cluster_network_policy" {
  description = "Disables Kubernetes Network Policy for Ray Clusters for this demo. Defaulting to 'true' aka disabled pending fixes to the kuberay-monitoring module. This should be defaulted to false."
  type        = bool
  default     = false
}

variable "additional_labels" {
  // string is used instead of map(string) since blueprint metadata does not support maps.
  type        = string
  description = "Additional labels to add to Kubernetes resources."
  default     = "created-by=ai-on-gke,ai.gke.io=ray"
}
