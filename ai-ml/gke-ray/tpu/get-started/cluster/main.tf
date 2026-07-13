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

# Get-started cluster. GKE with the Ray Operator add-on, one single-host TPU
# v6e slice (spot), and kube-prometheus-stack (Prometheus, Grafana, Ray
# dashboards).

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.30.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.13.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.ray.endpoint}"
  cluster_ca_certificate = base64decode(google_container_cluster.ray.master_auth[0].cluster_ca_certificate)
  token                  = data.google_client_config.default.access_token
}

provider "helm" {
  kubernetes = {
    host                   = "https://${google_container_cluster.ray.endpoint}"
    cluster_ca_certificate = base64decode(google_container_cluster.ray.master_auth[0].cluster_ca_certificate)
    token                  = data.google_client_config.default.access_token
  }
}

data "google_client_config" "default" {}

# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "container.googleapis.com",
    "tpu.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# Artifact Registry for the Ray Serve LLM on TPU image (see serve/Dockerfile).
resource "google_artifact_registry_repository" "ray_tpu" {
  location      = var.region
  repository_id = "ray-tpu"
  format        = "DOCKER"
  description   = "Ray Serve LLM on TPU images"

  depends_on = [google_project_service.apis]
}

# Nodes use the cloud-platform scope and the workload SA has project-level
# Artifact Registry read, so pods pull without a repo-scoped IAM binding.
# If your org restricts that, grant the SA roles/artifactregistry.reader.

# Service account for GKE workloads (Ray head and TPU workers)
resource "google_service_account" "gke_workload" {
  account_id   = "ray-tpu-workload"
  display_name = "GKE workload SA for ${var.cluster_name}"

  depends_on = [google_project_service.apis]
}

resource "google_project_iam_member" "workload_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

resource "google_project_iam_member" "workload_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# GCS bucket for prepared datasets and checkpoints. The workload SA gets
# object admin so Ray jobs read and write it.
resource "google_storage_bucket" "data" {
  name                        = coalesce(var.data_bucket_name, "${var.project_id}-ray-tpu-data")
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "workload_data" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.gke_workload.email}"
}

# pyarrow's GCS driver calls GetBucketMetadata (storage.buckets.get) when it
# creates the output directory, which objectAdmin alone doesn't grant. Add
# bucket read so Ray Data can write parquet and JSONL to this bucket.
resource "google_storage_bucket_iam_member" "workload_data_bucketread" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.gke_workload.email}"
}

# GKE cluster. The managed Ray Operator add-on installs KubeRay and TPU webhook
resource "google_container_cluster" "ray" {
  name     = var.cluster_name
  location = var.zone

  min_master_version = var.cluster_version

  network    = var.network
  subnetwork = var.subnetwork

  initial_node_count       = 1
  remove_default_node_pool = true
  deletion_protection      = false

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "RAPID"
  }

  addons_config {
    ray_operator_config {
      enabled = true
    }
    gcs_fuse_csi_driver_config {
      enabled = true
    }
  }

  depends_on = [google_project_service.apis]
}

# CPU node pool. Ray head and Serve controller live here
resource "google_container_node_pool" "cpu" {
  name     = "cpu-np"
  location = var.zone
  cluster  = google_container_cluster.ray.name

  node_count = var.num_cpu_nodes

  node_config {
    machine_type    = var.cpu_machine_type
    service_account = google_service_account.gke_workload.email

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }
}

# TPU node pool. Single-host slices (nodes_per_slice of 1) must not set a
# tpu_topology. Multi-host slices need COMPACT placement and a tpu_topology so
# GKE provisions the VMs as one physical slice.
resource "google_container_node_pool" "tpu_slices" {
  count = var.num_tpu_slices

  name     = "tpu-np-${count.index + 1}"
  location = var.zone
  cluster  = google_container_cluster.ray.name

  node_count = var.nodes_per_slice

  node_config {
    machine_type    = var.tpu_machine_type
    service_account = google_service_account.gke_workload.email
    spot            = var.tpu_spot

    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    gcfs_config {
      enabled = true
    }

    # Use a specific reservation when named, otherwise pin NO_RESERVATION explicitly
    # (GKE TPU node pools need the affinity stated, not left default).
    dynamic "reservation_affinity" {
      for_each = var.tpu_reservation != "" ? [1] : []
      content {
        consume_reservation_type = "SPECIFIC_RESERVATION"
        key                      = "compute.googleapis.com/reservation-name"
        values                   = [var.tpu_reservation]
      }
    }

    dynamic "reservation_affinity" {
      for_each = var.tpu_reservation == "" ? [1] : []
      content {
        consume_reservation_type = "NO_RESERVATION"
      }
    }
  }

  # Only multi-host slices take a topology and placement policy.
  dynamic "placement_policy" {
    for_each = var.nodes_per_slice > 1 ? [1] : []
    content {
      type         = "COMPACT"
      tpu_topology = var.tpu_topology
    }
  }
}

# K8s service account bound to the workload GSA (Workload Identity)
resource "kubernetes_service_account_v1" "ray" {
  metadata {
    name      = var.ksa_name
    namespace = "default"
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.gke_workload.email
    }
  }

  depends_on = [google_container_node_pool.cpu]
}

resource "google_service_account_iam_member" "ray_wi" {
  service_account_id = google_service_account.gke_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/${var.ksa_name}]"
}

# Optional HuggingFace token in Secret Manager (only if you pull a gated model).
# The workload SA gets accessor and a mirrored k8s Secret lets pods consume it.
# Created only when hf_token is non-empty.
resource "google_secret_manager_secret" "hf_token" {
  count     = var.hf_token != "" ? 1 : 0
  secret_id = "${var.cluster_name}-hf-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "hf_token" {
  count       = var.hf_token != "" ? 1 : 0
  secret      = google_secret_manager_secret.hf_token[0].id
  secret_data = var.hf_token
}

resource "google_secret_manager_secret_iam_member" "hf_token_accessor" {
  count     = var.hf_token != "" ? 1 : 0
  secret_id = google_secret_manager_secret.hf_token[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gke_workload.email}"
}

resource "kubernetes_secret_v1" "hf_token" {
  count = var.hf_token != "" ? 1 : 0

  metadata {
    name      = "hf-token"
    namespace = "default"
  }

  data = {
    token = var.hf_token
  }

  depends_on = [google_container_node_pool.cpu]
}

# Optional Weights and Biases API key in Secret Manager (only if you enable
# WandB in the training sample). Same pattern as the HF token. Created only when
# wandb_api_key is non-empty.
resource "google_secret_manager_secret" "wandb_api_key" {
  count     = var.wandb_api_key != "" ? 1 : 0
  secret_id = "${var.cluster_name}-wandb-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "wandb_api_key" {
  count       = var.wandb_api_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.wandb_api_key[0].id
  secret_data = var.wandb_api_key
}

resource "google_secret_manager_secret_iam_member" "wandb_accessor" {
  count     = var.wandb_api_key != "" ? 1 : 0
  secret_id = google_secret_manager_secret.wandb_api_key[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.gke_workload.email}"
}

resource "kubernetes_secret_v1" "wandb_api_key" {
  count = var.wandb_api_key != "" ? 1 : 0

  metadata {
    name      = "wandb-api-key"
    namespace = "default"
  }

  data = {
    key = var.wandb_api_key
  }

  depends_on = [google_container_node_pool.cpu]
}

# Prometheus and Grafana (kube-prometheus-stack) with Ray Grafana dashboards
resource "kubernetes_namespace_v1" "prometheus" {
  metadata {
    name = "prometheus-system"
  }

  depends_on = [google_container_node_pool.cpu]
}

resource "helm_release" "prometheus" {
  name       = "prometheus-stack"
  namespace  = kubernetes_namespace_v1.prometheus.metadata[0].name
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-prometheus-stack"

  values  = [file("${path.module}/monitoring/prometheus-values.yaml")]
  timeout = 600

  depends_on = [kubernetes_namespace_v1.prometheus]
}

resource "kubernetes_config_map_v1" "ray_dashboards" {
  for_each = fileset("${path.module}/monitoring/dashboards", "*_grafana_dashboard.json")

  metadata {
    name      = "ray-${replace(trimsuffix(each.value, "_grafana_dashboard.json"), "_", "-")}-dashboard"
    namespace = kubernetes_namespace_v1.prometheus.metadata[0].name
    labels = {
      grafana_dashboard = "1"
    }
  }
  binary_data = {
    (each.value) = filebase64("${path.module}/monitoring/dashboards/${each.value}")
  }

  depends_on = [helm_release.prometheus]
}
