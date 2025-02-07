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

# GKE cluster
resource "google_container_cluster" "ml_cluster" {
  name                     = var.cluster_name
  location                 = var.region
  count                    = var.enable_autopilot == false ? 1 : 0
  remove_default_node_pool = true
  initial_node_count       = 1
  min_master_version       = "1.28"

  logging_config {
    enable_components = ["SYSTEM_COMPONENTS", "WORKLOADS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = "true"
    }
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  addons_config {
    gcs_fuse_csi_driver_config {
      enabled = true
    }
  }

  release_channel {
    channel = "RAPID"
  }

  resource_labels = var.cluster_labels
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
    machine_type = "n1-standard-16"
  }
}

resource "google_container_node_pool" "gpu_pool" {
  name       = "gpu-pool"
  location   = var.region
  node_count = var.num_nodes
  count      = var.enable_autopilot || var.enable_tpu ? 0 : 1
  cluster    = var.enable_autopilot || var.enable_tpu ? null : google_container_cluster.ml_cluster[0].name

  node_locations = var.gpu_pool_node_locations
  
  autoscaling {
    min_node_count = "1"
    max_node_count = "3"
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

    labels = {
      "cloud.google.com/gke-profile" = "ray"
      env                            = var.project_id
    }

    guest_accelerator {
      type  = var.gpu_pool_accelerator_type
      count = 2
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
}

resource "google_container_node_pool" "tpu_pool" {
  provider           = google-beta
  name               = "tpu-pool"
  location           = var.region
  node_locations     = ["us-central2-b"]
  cluster            = var.enable_autopilot == false && var.enable_tpu ? google_container_cluster.ml_cluster[0].name : null
  initial_node_count = var.num_nodes
  count              = var.enable_autopilot == false && var.enable_tpu ? 1 : 0

  node_config {
    machine_type = "ct4p-hightpu-4t"
    oauth_scopes = [
      "https://www.googleapis.com/auth/logging.write",
      "https://www.googleapis.com/auth/monitoring",
      "https://www.googleapis.com/auth/devstorage.read_only",
      "https://www.googleapis.com/auth/trace.append",
      "https://www.googleapis.com/auth/service.management.readonly",
      "https://www.googleapis.com/auth/servicecontrol",
    ]

    labels = {
      "cloud.google.com/gke-profile" = "ray"
      env                            = var.project_id
    }
  }

  placement_policy {
    tpu_topology = "2x2x1"
    type         = "COMPACT"
  }
}