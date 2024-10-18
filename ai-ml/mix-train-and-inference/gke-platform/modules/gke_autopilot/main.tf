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
  region  = var.region
}

data "google_service_account" "default" {
  account_id = var.service_account
}

# GKE cluster
resource "google_container_cluster" "ml_cluster" {
  name     = var.cluster_name
  location = var.region
  count    = var.enable_autopilot == true ? 1 : 0

  initial_node_count = 1

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }
  node_config {
    # Google recommends custom service accounts that have cloud-platform scope and permissions granted via IAM Roles.
    service_account = data.google_service_account.default.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
    reservation_affinity {
      consume_reservation_type = "NO_RESERVATION"
    }
  }
  cluster_autoscaling {
    auto_provisioning_defaults {
      service_account = data.google_service_account.default.email
      oauth_scopes = [
        "https://www.googleapis.com/auth/cloud-platform"
      ]
    }
  }
  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = "true"
    }
  }

  dynamic "fleet" {
    for_each = var.enable_fleet ? [1] : []
    content {
      project = var.fleet_project_id
    }
  }

  ip_allocation_policy {
    cluster_ipv4_cidr_block  = ""
    services_ipv4_cidr_block = ""
  }

  enable_autopilot = true

  release_channel {
    channel = "RAPID"
  }

  min_master_version = "1.31"

  resource_labels = var.cluster_labels
}
