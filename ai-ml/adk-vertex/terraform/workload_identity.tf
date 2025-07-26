# Copyright 2025 Google LLC
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

locals {
  iam_service_account_name = var.iam_service_account_name != "" ? var.iam_service_account_name : var.default_resource_name
  k8s_service_account_name = var.k8s_service_account_name != "" ? var.k8s_service_account_name : var.default_resource_name
}

resource "google_project_iam_custom_role" "vertexai_custom_role" {
  project = var.project_id
  role_id = var.vertexai_custom_role_role_id
  title   = var.vertexai_custom_role_role_title
  permissions = [
    "aiplatform.endpoints.predict"
  ]
}

module "aiplatform_workload_identity" {
  providers = {
    kubernetes = kubernetes.adk
  }
  source                          = "terraform-google-modules/kubernetes-engine/google//modules/workload-identity"
  name                            = local.iam_service_account_name
  k8s_sa_name                     = local.k8s_service_account_name
  automount_service_account_token = true
  namespace                       = var.kubernetes_namespace
  roles = [
    "projects/${var.project_id}/roles/${var.vertexai_custom_role_role_id}",
  ]
  project_id = var.project_id
  depends_on = [module.gke_cluster, google_project_iam_custom_role.vertexai_custom_role]
}
