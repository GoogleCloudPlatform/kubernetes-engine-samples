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

# [START gke_aiml_anthropic_agent_sandbox_terraform_main]
resource "google_project_service" "required" {
  for_each = toset([
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.key
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# GKE Autopilot — Agent Sandbox add-on + FQDN NetworkPolicy (Dataplane V2)
# ---------------------------------------------------------------------------
resource "google_container_cluster" "this" {
  provider = google-beta

  name             = var.cluster_name
  location         = var.region
  enable_autopilot = true
  deletion_protection = false

  min_master_version = var.gke_min_version
  release_channel {
    channel = "RAPID"
  }

  enable_fqdn_network_policy = true

  secret_manager_config {
    enabled = true
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  depends_on = [google_project_service.required]
}

# Agent Sandbox add-on is not yet in the google-beta provider; enable via gcloud.
resource "null_resource" "enable_agent_sandbox" {
  triggers = {
    cluster = google_container_cluster.this.id
  }
  provisioner "local-exec" {
    command = <<-EOT
      gcloud beta container clusters update ${google_container_cluster.this.name} \
        --enable-agent-sandbox \
        --region ${var.region} --project ${var.project_id}
    EOT
  }
}

# ---------------------------------------------------------------------------
# Artifact Registry — worker / dispatcher / stats-adapter images
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "images" {
  repository_id = "anthropic-agents"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.required]
}

# ---------------------------------------------------------------------------
# Secret Manager — two secrets, two trust levels
# ---------------------------------------------------------------------------
resource "google_secret_manager_secret" "env_key" {
  secret_id = "anthropic-environment-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "env_key" {
  secret      = google_secret_manager_secret.env_key.id
  secret_data = var.anthropic_environment_key
}

resource "google_secret_manager_secret" "api_key" {
  secret_id = "anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "api_key" {
  secret      = google_secret_manager_secret.api_key.id
  secret_data = var.anthropic_api_key
}

# ---------------------------------------------------------------------------
# Workload Identity — one GSA per in-cluster component, least-privilege
# ---------------------------------------------------------------------------
locals {
  secrets = {
    env_key = google_secret_manager_secret.env_key
    api_key = google_secret_manager_secret.api_key
  }
  components = {
    dispatcher = {
      ksa     = "dispatcher"
      secrets = ["env_key"]
      roles   = []
    }
    stats-adapter = {
      ksa     = "stats-adapter"
      secrets = ["api_key"]
      roles   = ["roles/monitoring.metricWriter"]
    }
    # The worker GSA holds NO project roles — only bucket-scoped objectUser
    # (granted in storage.tf). It exists so the GCS FUSE sidecar can auth via
    # Workload Identity; the worker container itself still has
    # automountServiceAccountToken: false.
    worker = {
      ksa     = "claude-agent-worker"
      secrets = []
      roles   = []
    }
  }
}

resource "google_service_account" "component" {
  for_each     = local.components
  account_id   = "anthropic-${each.key}"
  display_name = "Anthropic Managed Agents — ${each.key}"
}

resource "google_service_account_iam_member" "wif" {
  for_each           = local.components
  service_account_id = google_service_account.component[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${each.value.ksa}]"
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = {
    for pair in flatten([
      for comp, cfg in local.components : [
        for s in cfg.secrets : { comp = comp, secret = s }
      ]
    ]) : "${pair.comp}/${pair.secret}" => pair
  }
  secret_id = local.secrets[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.component[each.value.comp].member
}

resource "google_project_iam_member" "component_roles" {
  for_each = {
    for pair in flatten([
      for comp, cfg in local.components : [
        for r in cfg.roles : { comp = comp, role = r }
      ]
    ]) : "${pair.comp}/${pair.role}" => pair
  }
  project = var.project_id
  role    = each.value.role
  member  = google_service_account.component[each.value.comp].member
}
# [END gke_aiml_anthropic_agent_sandbox_terraform_main]
