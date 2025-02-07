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

# create private subnet
module "network" {
  source         = "../modules/network"
  project_id     = var.project_id
  region         = var.region
  cluster_prefix = var.cluster_prefix
}

# [START gke_databases_elasticsearch_standard_private_regional_cluster]
module "elasticsearch_cluster" {
  source                   = "../modules/cluster"
  project_id               = var.project_id
  region                   = var.region
  cluster_prefix           = var.cluster_prefix
  network                  = module.network.network_name
  subnetwork               = module.network.subnet_name

  node_pools = [
    {
      name            = "pool-elastic"
      disk_size_gb    = var.node_disk_size
      disk_type       = var.node_disk_type
      autoscaling     = true
      min_count       = 1
      max_count       = var.autoscaling_max_count
      max_surge       = 1
      max_unavailable = 0
      machine_type    = var.node_machine_type
      auto_repair     = true
    }
  ]
  node_pools_labels = {
    all = {}
    pool-elastic = {
      "app.stateful/component" = "elasticsearch"
    }
  }
  node_pools_taints = {
    all = []
  }
}

output "kubectl_connection_command" {
  value       = "gcloud container clusters get-credentials ${var.cluster_prefix}-cluster --region ${var.region}"
  description = "Connection command"
}
# [END gke_databases_elasticsearch_standard_private_regional_cluster]