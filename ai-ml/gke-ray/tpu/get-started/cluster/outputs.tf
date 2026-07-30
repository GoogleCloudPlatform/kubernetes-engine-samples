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

output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.ray.name
}

output "cluster_zone" {
  description = "GKE cluster zone"
  value       = google_container_cluster.ray.location
}

output "tpu_node_pools" {
  description = "TPU node pool names (one per slice)"
  value       = [for np in google_container_node_pool.tpu_slices : np.name]
}

output "workload_service_account" {
  description = "GKE workload service account email"
  value       = google_service_account.gke_workload.email
}

output "k8s_service_account" {
  description = "K8s service account name (Workload Identity)"
  value       = kubernetes_service_account_v1.ray.metadata[0].name
}

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "artifact_registry_repo" {
  description = "Artifact Registry Docker repo path for the serve image"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.ray_tpu.repository_id}"
}

output "data_bucket" {
  description = "GCS bucket for prepared datasets + checkpoints"
  value       = "gs://${google_storage_bucket.data.name}"
}

output "hf_secret_name" {
  description = "Secret Manager secret holding the HF token (empty if none set)"
  value       = length(google_secret_manager_secret.hf_token) > 0 ? google_secret_manager_secret.hf_token[0].secret_id : ""
}
