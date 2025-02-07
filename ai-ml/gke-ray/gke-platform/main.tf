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

data "google_client_config" "provider" {}

data "google_container_cluster" "ml_cluster" {
  name       = var.cluster_name
  location   = var.region
  depends_on = [module.gke_autopilot, module.gke_standard]
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

provider "kubernetes" {
  host  = data.google_container_cluster.ml_cluster.endpoint
  token = data.google_client_config.provider.access_token
  cluster_ca_certificate = base64decode(
    data.google_container_cluster.ml_cluster.master_auth[0].cluster_ca_certificate
  )
}

provider "kubectl" {
  host  = data.google_container_cluster.ml_cluster.endpoint
  token = data.google_client_config.provider.access_token
  cluster_ca_certificate = base64decode(
    data.google_container_cluster.ml_cluster.master_auth[0].cluster_ca_certificate
  )
}

provider "helm" {
  kubernetes {
    ##config_path = pathexpand("~/.kube/config")
    host  = data.google_container_cluster.ml_cluster.endpoint
    token = data.google_client_config.provider.access_token
    cluster_ca_certificate = base64decode(
      data.google_container_cluster.ml_cluster.master_auth[0].cluster_ca_certificate
    )
  }
}

module "gke_autopilot" {
  source = "./modules/gke_autopilot"

  project_id       = var.project_id
  region           = var.region
  cluster_name     = var.cluster_name
  cluster_labels   = var.cluster_labels
  enable_autopilot = var.enable_autopilot
}


module "gke_standard" {
  source = "./modules/gke_standard"

  project_id                = var.project_id
  region                    = var.region
  cluster_name              = var.cluster_name
  cluster_labels            = var.cluster_labels
  enable_autopilot          = var.enable_autopilot
  enable_tpu                = var.enable_tpu
  gpu_pool_machine_type     = var.gpu_pool_machine_type
  gpu_pool_accelerator_type = var.gpu_pool_accelerator_type
  gpu_pool_node_locations   = var.gpu_pool_node_locations
}

module "kubernetes" {
  source = "./modules/kubernetes"

  depends_on       = [module.gke_standard]
  region           = var.region
  cluster_name     = var.cluster_name
  enable_autopilot = var.enable_autopilot
  enable_tpu       = var.enable_tpu
}

module "kuberay" {
  source = "./modules/kuberay"

  depends_on       = [module.gke_autopilot, module.gke_standard]
  region           = var.region
  cluster_name     = var.cluster_name
  enable_autopilot = var.enable_autopilot
}
