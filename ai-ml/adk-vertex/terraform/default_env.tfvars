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

project_id            = "<PROJECT_ID>"
default_resource_name = "adk-tf"

cluster_name      = "" # Leave empty to use the default name (default_resource_name) 
cluster_location  = "us-central1"
private_cluster   = false
autopilot_cluster = true

network_name      = "" # Leave empty to use the default name
subnetwork_name   = "" # Leave empty to use the default name
subnetwork_region = "us-central1"
subnetwork_cidr   = "10.128.0.0/20"

kubernetes_namespace = "default"

image_repository_name = ""


iam_service_account_name = ""
k8s_service_account_name = ""

