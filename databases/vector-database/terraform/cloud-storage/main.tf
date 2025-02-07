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
module "cloud_storage" {
  source         = "../modules/cloud-storage"
  project_id     = var.project_id
  region         = var.region
  cluster_prefix = var.cluster_prefix
  db_namespace   = var.db_namespace
}

output "bucket_name" {
  value       = module.cloud_storage.bucket_name
  description = "Cloud Storage bucket name"
}

output "service_account_bucket_name" {
  value       = module.cloud_storage.service_account_bucket_name
  description = "Service Account to access the bucket"
}

output "service_account_eventarc_name" {
  value       = module.cloud_storage.service_account_eventarc_name
  description = "Service Account to access the Pub/Sub topic and GKE clusters for Eventarc"
}


# [END gke_databases_vector_database_cloud_storage_bucket]

