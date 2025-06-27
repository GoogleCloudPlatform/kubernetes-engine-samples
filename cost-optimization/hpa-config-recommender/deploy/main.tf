# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.20"
    }
  }
  provider_meta "google" {
      module_name = "cloud-solutions/gke-wa-hpa-recommender-v1.1"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ************************************************** #
# Create BigQuery Dataset
# ************************************************** #
resource "google_bigquery_dataset" "gke_workload_metrics" {
  dataset_id  = var.dataset_id
  project     = var.project_id
  location    = var.region
  description = "Dataset for workload forecast metrics"
}

# ************************************************** #
# Create BigQuery Table
# ************************************************** #
resource "google_bigquery_table" "workload_recommendations" {
  dataset_id = google_bigquery_dataset.gke_workload_metrics.dataset_id
  table_id   = var.table_id
  project    = var.project_id
  deletion_protection = false

  schema = jsonencode([
    { name = "project_id", type = "STRING", mode = "NULLABLE" },
    { name = "cluster_name", type = "STRING", mode = "NULLABLE" },
    { name = "location", type = "STRING", mode = "NULLABLE" },
    { name = "namespace", type = "STRING", mode = "NULLABLE" },
    { name = "controller_name", type = "STRING", mode = "NULLABLE" },
    { name = "container_name", type = "STRING", mode = "NULLABLE" },
    { name = "analysis_period_start", type = "DATETIME", mode = "NULLABLE" },
    { name = "analysis_period_end", type = "DATETIME", mode = "NULLABLE" },
    { name = "window_begin", type = "DATETIME", mode = "NULLABLE" },
    { name = "num_replicas_at_usage_window", type = "INTEGER", mode = "NULLABLE" },
    { name = "sum_containers_cpu_request", type = "FLOAT", mode = "NULLABLE" },
    { name = "sum_containers_cpu_usage", type = "FLOAT", mode = "NULLABLE" },
    { name = "forecast_sum_cpu_up_and_running", type = "FLOAT", mode = "NULLABLE" },
    { name = "sum_containers_mem_request_mi", type = "FLOAT", mode = "NULLABLE" },
    { name = "sum_containers_mem_usage_mi", type = "FLOAT", mode = "NULLABLE" },
    { name = "forecast_sum_mem_up_and_running", type = "FLOAT", mode = "NULLABLE" },
    { name = "forecast_replicas_up_and_running", type = "INTEGER", mode = "NULLABLE" },
    { name = "forecast_mem_saving_mi", type = "FLOAT", mode = "NULLABLE" },
    { name = "forecast_cpu_saving", type = "FLOAT", mode = "NULLABLE" },
    { name = "recommended_cpu_request", type = "FLOAT", mode = "NULLABLE" },
    { name = "recommended_mem_request_and_limits_mi", type = "FLOAT", mode = "NULLABLE" },
    { name = "recommended_cpu_limit_or_unbounded", type = "FLOAT", mode = "NULLABLE" },
    { name = "recommended_min_replicas", type = "INTEGER", mode = "NULLABLE" },
    { name = "recommended_max_replicas", type = "INTEGER", mode = "NULLABLE" },
    { name = "recommended_hpa_target_cpu", type = "FLOAT", mode = "NULLABLE" },
    { name = "max_usage_slope_up_ratio", type = "FLOAT", mode = "NULLABLE" },
    { name = "workload_e2e_startup_latency_rows", type = "INTEGER", mode = "NULLABLE" },
    { name = "method", type = "STRING", mode = "NULLABLE" }
  ])
}

# ************************************************** #
# Create Artifact Registry for Python Packages
# ************************************************** #
resource "google_artifact_registry_repository" "python_registry" {
  provider      = google
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_registry_id
  format        = "PYTHON"

  description = "Artifact Registry for storing Python packages related to workload forecasting"
}
