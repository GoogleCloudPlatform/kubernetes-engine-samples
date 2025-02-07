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

# [START gke_databases_elasticsearch_vpc_multi_region_network]
module "gcp-network" {
  source  = "terraform-google-modules/network/google"
  version = "~> 8.1.0"

  project_id   = var.project_id
  network_name = "${var.cluster_prefix}-vpc"

  subnets = [
    {
      subnet_name           = "${var.cluster_prefix}-private-subnet"
      subnet_ip             = "10.10.0.0/24"
      subnet_region         = var.region
      subnet_private_access = true
      subnet_flow_logs      = "true"
    }
  ]

  secondary_ranges = {
    ("${var.cluster_prefix}-private-subnet") = [
      {
        range_name    = "k8s-pod-range"
        ip_cidr_range = "10.48.0.0/20"
      },
      {
        range_name    = "k8s-service-range"
        ip_cidr_range = "10.52.0.0/20"
      },
    ]
  }
}

output "network_name" {
  value = module.gcp-network.network_name
}

output "subnet_name" {
  value = module.gcp-network.subnets_names[0]
}
# [END gke_databases_elasticsearch_vpc_multi_region_network]

# [START gke_databases_elasticsearch_cloudnat_simple_create]
module "cloud_router" {
  source  = "terraform-google-modules/cloud-router/google"
  version = "~> 6.0"
  project = var.project_id 
  name    = "${var.cluster_prefix}-nat-router"
  network = module.gcp-network.network_name
  region  = var.region
  nats = [{
    name = "${var.cluster_prefix}-nat"
  }]
}
# [END gke_databases_elasticsearch_cloudnat_simple_create]