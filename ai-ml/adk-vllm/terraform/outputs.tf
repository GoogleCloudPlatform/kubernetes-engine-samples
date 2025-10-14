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

# output "grafana_uri" {
#   value = module.kuberay-monitoring[0].grafana_uri
# }

# output "ray_cluster_uri" {
#   value = module.kuberay-cluster[0].ray_cluster_uri != "" ? "http://${module.kuberay-cluster[0].ray_cluster_uri}" : local.ray_cluster_default_uri
# }

output "kubernetes_namespace" {
  value       = local.kubernetes_namespace
  description = "Kubernetes namespace"
}

output "gke_cluster_name" {
  value       = local.cluster_name
  description = "GKE cluster name"
}

output "gke_cluster_location" {
  value       = var.cluster_location
  description = "GKE cluster location"
}

output "project_id" {
  value       = var.project_id
  description = "GKE cluster location"
}

# output "ray_dashboard_uri" {
#   description = "Ray Dashboard Endpoint to access user interface. In case of private IP, consider port-forwarding."
#   value       = module.kuberay-cluster[0].ray_dashboard_uri != "" ? "http://${module.kuberay-cluster[0].ray_dashboard_uri}" : ""
# }

# output "ray_dashboard_ip_address" {
#   description = "Ray Dashboard global IP address"
#   value       = module.kuberay-cluster[0].ray_dashboard_ip_address
# }