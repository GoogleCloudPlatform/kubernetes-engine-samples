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

# [START gke_databases_vector_database_cloud_storage_bucket]
module "cloud-storage" {
  source        = "terraform-google-modules/cloud-storage/google//modules/simple_bucket"
  version       = "~> 5.0"

  name          = "${var.project_id}-${var.cluster_prefix}-training-docs"
  project_id    = var.project_id
  location      = var.region
  force_destroy = true
}

# use to set permissions with the dynamic SA

module "cloud-storage-iam-bindings" {
  source          = "terraform-google-modules/iam/google//modules/storage_buckets_iam"
  version         = "~> 7.0"

  storage_buckets = [module.cloud-storage.name]
  mode            = "authoritative"
  bindings        = {
    "roles/storage.objectViewer" = ["${module.service-account-bucket.iam_email}"]
  }

  depends_on      = [module.cloud-storage, module.service-account-bucket.iam_email]
}

module "service-account-bucket" {
  source          = "terraform-google-modules/service-accounts/google"
  version         = "~> 4.0"

  project_id      = var.project_id
  names           = ["${var.cluster_prefix}-bucket-access"]
  description     = "Service account to access the bucket with training documents"
}

module "project-iam-bindings-bucket" {
  source     = "terraform-google-modules/iam/google//modules/projects_iam"
  version    = "~> 7.0"

  projects   = ["${var.project_id}"]
  mode       = "additive"

  bindings = {
    "roles/aiplatform.user"          = ["serviceAccount:${var.cluster_prefix}-bucket-access@${var.project_id}.iam.gserviceaccount.com"] 
    "roles/iam.workloadIdentityUser" = ["serviceAccount:${var.project_id}.svc.id.goog[${var.db_namespace}/embed-docs-sa]"] 
  } 

  depends_on = [module.service-account-bucket]
}

data "google_storage_project_service_account" "gcs_account" {
  project      = var.project_id
}

module "project-iam-bindings-cloud-storage" {
  source     = "terraform-google-modules/iam/google//modules/projects_iam"
  version    = "~> 7.0"

  projects   = ["${var.project_id}"]
  mode       = "additive"

  bindings = {
    "roles/pubsub.publisher"          = ["serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"] 
  } 
}

output "bucket_name" {
  value = module.cloud-storage.name
}

output "service_account_bucket_name" {
  value = module.service-account-bucket.email
}

# [END gke_databases_vector_database_cloud_storage_bucket]

