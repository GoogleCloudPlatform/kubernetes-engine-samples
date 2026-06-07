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

output "cluster_name" {
  value = google_container_cluster.this.name
}

output "cluster_location" {
  value = google_container_cluster.this.location
}

output "artifact_registry" {
  description = "Docker repo path prefix for built images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "dispatcher_gsa" {
  value = google_service_account.component["dispatcher"].email
}

output "stats_adapter_gsa" {
  value = google_service_account.component["stats-adapter"].email
}

output "worker_gsa" {
  value = google_service_account.component["worker"].email
}

output "session_outputs_bucket" {
  value = google_storage_bucket.session_outputs.name
}
