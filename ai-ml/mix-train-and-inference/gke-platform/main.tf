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

provider "google" {
  project = var.project_id
}

provider "google-beta" {
  project = var.project_id
}

resource "google_service_account" "service_account" {
  account_id   = "gke-llm-sa"
  display_name = "LLM clusters Service Account"
}

# Grant permissions to write metrics for monitoring purposes
resource "google_project_iam_member" "project" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.service_account.email}"
}

module "gke_autopilot" {
  source = "./modules/gke_autopilot"

  project_id       = var.project_id
  region           = var.region
  cluster_name     = var.cluster_name
  cluster_labels   = var.cluster_labels
  enable_autopilot = var.enable_autopilot
  service_account  = google_service_account.service_account.email
  enable_fleet     = var.enable_fleet
  fleet_project_id = var.fleet_project_id
}



module "gke_standard" {
  source = "./modules/gke_standard"

  project_id                = var.project_id
  region                    = var.region
  cluster_name              = var.cluster_name
  cluster_labels            = var.cluster_labels
  enable_autopilot          = var.enable_autopilot
  gpu_pool_machine_type     = var.gpu_pool_machine_type
  gpu_pool_accelerator_type = var.gpu_pool_accelerator_type
  gpu_pool_node_locations   = var.gpu_pool_node_locations
  service_account           = google_service_account.service_account.email
  enable_fleet              = var.enable_fleet
  fleet_project_id          = var.fleet_project_id
  gateway_api_channel       = var.gateway_api_channel
}
