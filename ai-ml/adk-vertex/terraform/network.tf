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
  network_name    = var.network_name != "" ? var.network_name : var.default_resource_name
  subnetwork_name = var.subnetwork_name != "" ? var.subnetwork_name : var.default_resource_name
}

module "custom_network" {
  source       = "github.com/ai-on-gke/common-infra/common/modules/gcp-network"
  project_id   = var.project_id
  network_name = local.network_name
  create_psa   = true

  subnets = [
    {
      subnet_name           = local.subnetwork_name
      subnet_ip             = var.subnetwork_cidr
      subnet_region         = var.subnetwork_region
      subnet_private_access = var.subnetwork_private_access
      description           = "Network for Google ADK tutorial"
    }
  ]
}
