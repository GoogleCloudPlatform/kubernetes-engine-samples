/**
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

# --- Enable Google Cloud APIs ---
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "servicenetworking.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
  project = var.project_id
  service = each.key
}

# --- IAM Service Accounts ---

# Service Account for GKE Nodes
resource "google_service_account" "gke_node_sa" {
  project      = var.project_id
  account_id   = var.gke_node_sa_name
  display_name = "GKE Node SA (${var.cluster_name})"
  depends_on   = [google_project_service.required_apis]
}

# Minimal Roles for GKE Nodes (Monitoring, Logging, Image Pulling)
resource "google_project_iam_member" "gke_node_sa_roles" {
  for_each = toset([
    "roles/monitoring.viewer",
    "roles/logging.logWriter",
    "roles/storage.objectViewer",
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.gke_node_sa.email}"
}

# Service Account for WordPress Application (Workload Identity)
resource "google_service_account" "wordpress_app_sa" {
  project      = var.project_id
  account_id   = var.wordpress_app_sa_name
  display_name = "WordPress App SA (${var.cluster_name})"
  depends_on   = [google_project_service.required_apis]
}

# Grant WordPress App SA permission to connect to Cloud SQL
resource "google_project_iam_member" "wordpress_app_sa_sqlclient" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.wordpress_app_sa.email}"
}

# Allow Kubernetes Service Account to impersonate Google SA
resource "google_service_account_iam_member" "wordpress_ksa_wi_binding" {
  service_account_id = google_service_account.wordpress_app_sa.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/${var.kubernetes_service_account_name}]"
  depends_on         = [google_service_account.wordpress_app_sa]
}

# --- GKE Cluster ---
resource "google_container_cluster" "primary" {
  project                  = var.project_id
  name                     = var.cluster_name
  location                 = var.zone
  remove_default_node_pool = true
  initial_node_count       = 1

  network_policy {
    enabled = true
  }

  # Enable Workload Identity
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
  deletion_protection = false
  depends_on = [google_project_service.required_apis]
}

# GKE Node Pool using dedicated Service Account
resource "google_container_node_pool" "primary_nodes" {
  project    = var.project_id
  name       = "${var.cluster_name}-node-pool"
  location   = google_container_cluster.primary.location
  cluster    = google_container_cluster.primary.name
  node_count = var.gke_num_nodes

  node_config {
    machine_type    = var.machine_type
    service_account = google_service_account.gke_node_sa.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
  management {
    auto_repair  = true
    auto_upgrade = true
  }
  depends_on = [google_service_account.gke_node_sa]
}

# --- Cloud SQL Instance ---
resource "random_password" "sql_user_password" {
  length  = 16
  special = false
}

resource "google_sql_database_instance" "main" {
  project          = var.project_id
  name             = var.sql_instance_name
  database_version = var.sql_database_version
  region           = var.region
  settings {
    tier = var.sql_tier
    ip_configuration {
      ipv4_enabled = true
    }
    backup_configuration {
      enabled = false
    }
  }
  deletion_protection = false
  depends_on          = [google_project_service.required_apis]
}

resource "google_sql_database" "database" {
  project  = var.project_id
  name     = var.sql_database_name
  instance = google_sql_database_instance.main.name
}

resource "google_sql_user" "user" {
  project  = var.project_id
  name     = var.sql_user_name
  instance = google_sql_database_instance.main.name
  password = random_password.sql_user_password.result
}

# --- Kubernetes Provider Configuration ---
data "google_container_cluster" "cluster_data" {
  project    = var.project_id
  name       = google_container_cluster.primary.name
  location   = google_container_cluster.primary.location
  depends_on = [google_container_node_pool.primary_nodes]
}

provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.cluster_data.endpoint}"
  cluster_ca_certificate = base64decode(data.google_container_cluster.cluster_data.master_auth[0].cluster_ca_certificate)

  # Use gcloud to generate credentials dynamically based on your ADC
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "gke-gcloud-auth-plugin"
  }
}

# --- Kubernetes Resources ----
resource "kubernetes_service_account" "wordpress_ksa" {
  metadata {
    name      = var.kubernetes_service_account_name
    namespace = "default"
    annotations = {
      "iam.gke.io/gcp-service-account" = google_service_account.wordpress_app_sa.email
    }
  }
  depends_on = [google_service_account_iam_member.wordpress_ksa_wi_binding]
}

# Secret with DB User/Name (Password not needed for Proxy connection)
resource "kubernetes_secret" "db_details" {
  metadata {
    name      = "wordpress-db-details"
    namespace = "default"
  }
  data = {
    DB_NAME = google_sql_database.database.name
    DB_USER = google_sql_user.user.name
  }
  type       = "Opaque"
  depends_on = [google_sql_user.user]
}

# Persistent Volume Claim for Wordpress Storage
resource "kubernetes_manifest" "wp_pvc_manifest" {
  manifest = {
    "apiVersion" = "v1"
    "kind"       = "PersistentVolumeClaim"
    "metadata"   = {
      "name"      = "wp-pv-claim"
      "namespace" = "default"
      "labels"    = {
         "app" = "wordpress"
       }
    }
    "spec" = {
      "accessModes" = [
        "ReadWriteOnce",
      ]
      "resources" = {
        "requests" = {
          "storage" = "${var.wp_storage_size_gb}Gi"
        }
      }
      "storageClassName" = "standard-rwo"
    }
  }
}

# WordPress Deployment
resource "kubernetes_deployment" "wordpress" {
  metadata {
    name      = "wordpress"
    namespace = "default"
    labels    = { app = "wordpress" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "wordpress" } }

    template {
      metadata { labels = { app = "wordpress" } }

      spec {
        service_account_name = kubernetes_service_account.wordpress_ksa.metadata[0].name

        container {
          name  = "wordpress"
          image = "wordpress:latest"

          port {
            container_port = 80
            name           = "http"
          }

          env {
            name = "WORDPRESS_DB_HOST"
            value = "127.0.0.1:3306"
          }
          env {
            name = "WORDPRESS_DB_USER"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.db_details.metadata[0].name
                key  = "DB_USER"
              }
            }
          }
          env {
            name = "WORDPRESS_DB_NAME"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.db_details.metadata[0].name
                key  = "DB_NAME"
              }
            }
          }

          volume_mount {
            name       = "wordpress-persistent-storage"
            mount_path = "/var/www/html/wp-content"
          }

        }

        container {
          name  = "cloud-sql-proxy"
          image = "gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.18.0"
          args  = ["--structured-logs", "--port=3306", google_sql_database_instance.main.connection_name]

          security_context {
            run_as_non_root = true
          }

          resources {
            requests = {
              cpu    = "50m"
              memory = "64Mi"
            }
            # Optional: Add limits block if needed
            # limits = {
            #   cpu    = "100m"
            #   memory = "128Mi"
            # }
          }
        }

        volume {
          name = "wordpress-persistent-storage"
          persistent_volume_claim {
            claim_name = kubernetes_manifest.wp_pvc_manifest.manifest.metadata.name

          }
        }

      }
    }
  }

  depends_on = [
    kubernetes_service_account.wordpress_ksa,
    kubernetes_secret.db_details,
    kubernetes_manifest.wp_pvc_manifest
  ]
}

# WordPress Service (Type LoadBalancer)
resource "kubernetes_service" "wordpress" {

  metadata {
    name      = "wordpress"
    namespace = "default"
    labels    = { app = "wordpress" }
  }
  spec {
    selector = { app = "wordpress" }
    
    port {
      port = 80
      protocol = "TCP"
      name           = "http"
    }
    type     = "LoadBalancer"
  }
  depends_on = [kubernetes_deployment.wordpress]
}
