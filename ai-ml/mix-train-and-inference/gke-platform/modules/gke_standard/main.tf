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

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

locals {
  gateway_api_config = var.gateway_api_channel != null ? [{ channel : var.gateway_api_channel }] : []
}

# GKE cluster
resource "google_container_cluster" "ml_cluster" {
  name                     = var.cluster_name
  location                 = var.region
  count                    = var.enable_autopilot == false ? 1 : 0
  remove_default_node_pool = true
  initial_node_count       = 1
  min_master_version       = "1.30"

  node_config {
    service_account = data.google_service_account.default.email
    oauth_scopes = [
       "https://www.googleapis.com/auth/devstorage.read_only",
       "https://www.googleapis.com/auth/logging.write",
       "https://www.googleapis.com/auth/monitoring",
       "https://www.googleapis.com/auth/service.management.readonly",
       "https://www.googleapis.com/auth/servicecontrol",
       "https://www.googleapis.com/auth/trace.append",
    ]
  }
  
  logging_config {
    enable_components = [
      "APISERVER",
      "CONTROLLER_MANAGER",
      "SCHEDULER",
      "SYSTEM_COMPONENTS",
      "WORKLOADS"
    ]
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

  dynamic "gateway_api_config" {
    for_each = local.gateway_api_config

    content {
      channel = gateway_api_config.value.channel
    }
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }


  release_channel {
    channel = "RAPID"
  }

  resource_labels = var.cluster_labels

  addons_config {
    gcp_filestore_csi_driver_config {
      enabled = true
    }

    gcs_fuse_csi_driver_config {
      enabled = true
    }

    gce_persistent_disk_csi_driver_config {
      enabled = true
    }
  }
}

data "google_service_account" "default" {
  account_id = var.service_account
}

resource "google_container_node_pool" "cpu_pool" {
  name     = "cpu-pool"
  location = var.region
  count    = var.enable_autopilot ? 0 : 1
  cluster  = var.enable_autopilot ? null : google_container_cluster.ml_cluster[0].name

  autoscaling {
    min_node_count = 1
    max_node_count = 3
  }

  management {
    auto_repair  = "true"
    auto_upgrade = "true"
  }

  node_config {
    machine_type    = "n1-standard-4"
    service_account = data.google_service_account.default.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/trace.append",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
    ]
  }
}

resource "google_container_node_pool" "gpu_pool" {
  name       = "gpu-pool"
  location   = var.region
  node_count = var.num_nodes
  count      = var.enable_autopilot ? 0 : 1
  cluster    = var.enable_autopilot ? null : google_container_cluster.ml_cluster[0].name

  node_locations = var.gpu_pool_node_locations

  autoscaling {
    min_node_count = "1"
    max_node_count = "2"
  }

  management {
    auto_repair  = "true"
    auto_upgrade = "true"
  }

  node_config {
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/trace.append",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
    ]
    service_account = data.google_service_account.default.email
    
    gvnic {
      enabled = true
    }
    
    dynamic "taint" {
      for_each = var.ondemand_taints
      content {
        key    = taint.value.key
        value  = taint.value.taint_value
        effect = taint.value.effect
      }
    }
    labels = {
      "resource-type" : "ondemand"
    }

    guest_accelerator {
      type  = var.gpu_pool_accelerator_type
      count = 2
      gpu_driver_installation_config {
        gpu_driver_version = var.gpu_driver_version
      }
    }

    # preemptible  = true
    image_type   = "cos_containerd"
    machine_type = var.gpu_pool_machine_type
    tags         = ["gke-node", "${var.project_id}-gke"]

    disk_size_gb = "200"
    disk_type    = "pd-balanced"

    metadata = {
      disable-legacy-endpoints = "true"
    }
  }
  # queued_provisioning {
  #   enabled = true
  # }
}
