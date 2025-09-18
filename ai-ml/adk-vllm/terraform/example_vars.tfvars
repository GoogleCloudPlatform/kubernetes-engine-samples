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

##common variables
## Need to pull this variables from tf output from previous platform stage
project_id = "<PROJECT_ID>"

## this is required for terraform to connect to GKE master and deploy workloads
create_cluster   = true # this flag will create a new standard public gke cluster in default network
cluster_name     = "<CLUSTER_NAME>"
cluster_location = "us-east4"

#######################################################
####    APPLICATIONS
#######################################################

# Creates a google service account & k8s service account & configures workload identity with appropriate permissions.
# Set to false & update the variable `workload_identity_service_account` to use an existing IAM service account.
create_service_account = false

#DISABLE IAP
create_brand           = false
ray_dashboard_add_auth = false

autopilot_cluster = true

gpu_pools = [{
  name           = "gpu-pool-l4"
  machine_type   = "g2-standard-24"
  node_locations = "us-east4-c"
  autoscaling    = true

  min_count          = 0
  max_count          = 3
  accelerator_count  = 2
  disk_size_gb       = 200
  enable_gcfs        = true
  logging_variant    = "DEFAULT"
  disk_type          = "pd-balanced"
  accelerator_type   = "nvidia-l4"
  gpu_driver_version = "LATEST"
}]

enable_gpu = true
