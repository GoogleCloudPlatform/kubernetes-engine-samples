# Copyright 2024 Google LLC
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

# [START gke_databases_vector_database_cloud_storage_bucket_eventarc]

resource "google_eventarc_trigger" "trigger" {
  name            = "${var.cluster_prefix}-storage-trigger"
  location        = var.region
  project         = var.project_id
  service_account = module.service-account-eventarc.email

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = module.cloud-storage.name
  }
  destination {
    gke {
      cluster   = "${var.cluster_prefix}-cluster"
      location  = var.region
      namespace = var.db_namespace
      path      = "/"
      service   = "embed-docs"
    }
  }

  depends_on = [module.cloud-storage, module.project-iam-bindings]
}

# roles list https://cloud.google.com/eventarc/docs/gke/roles-permissions

module "project-iam-bindings" {
  source   = "terraform-google-modules/iam/google//modules/projects_iam"
  projects = ["${var.project_id}"]
  mode     = "additive"

  # because for_each loop can't work with unknown values even with configured depends_on parameter

  bindings = {
    "roles/pubsub.subscriber"       = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/pubsub.publisher"        = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/eventarc.admin"          = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"]
    "roles/eventarc.eventReceiver"  = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/iam.serviceAccountUser"  = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/monitoring.metricWriter" = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/container.admin"         = ["serviceAccount:${var.cluster_prefix}-eventarc-access@${var.project_id}.iam.gserviceaccount.com"] 
  } 

  depends_on = [module.cloud-storage, module.service-account-eventarc]
}

module "service-account-eventarc" {
  source       = "terraform-google-modules/service-accounts/google"
  version      = "~> 4.0"
  project_id   = var.project_id
  names        = ["${var.cluster_prefix}-eventarc-access"]
  description  = "Service account to access the Pub/Sub Topic and GKE clusters for Eventarc"
}

output "service_account_eventarc_name" {
  value = module.service-account-eventarc.email
}

# [END gke_databases_vector_database_cloud_storage_bucket_eventarc]

