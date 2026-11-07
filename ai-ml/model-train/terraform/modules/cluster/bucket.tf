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

# [START gke_model_train_cloud_storage_bucket]
module "cloud-storage" {
  source        = "terraform-google-modules/cloud-storage/google//modules/simple_bucket"
  version       = "~> 5.0"

  name          = "${var.project_id}-${var.cluster_prefix}-model-train"
  project_id    = var.project_id
  location      = var.region
  force_destroy = true
}

locals {
  workload_principal = "principal://iam.googleapis.com/projects/${data.google_project.project.number}/locations/global/workloadIdentityPools/${var.project_id}.svc.id.goog/subject/ns/default/sa/bucket-access"
}


module "cloud-storage-iam-bindings" {
  source          = "terraform-google-modules/iam/google//modules/storage_buckets_iam"
  version         = "~> 7.0"

  storage_buckets = [module.cloud-storage.name]
  mode            = "authoritative"
  bindings        = {
    "roles/storage.objectUser" = ["${local.workload_principal}"]
  }
  depends_on      = [module.cloud-storage]
}
# [END gke_model_train_cloud_storage_bucket]
