# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

export CLUSTER_NAME=dws-cluster
export REGION=europe-west2
export ZONE=$REGION-b
gcloud container clusters create ${CLUSTER_NAME} \
    --addons=RayOperator \
    --region=$REGION
    --cluster-version=${CLUSTER_VERSION}  \
    --machine-type=e2-standard-8 \
    --node-locations=$ZONE \
    --num-nodes=2

gcloud beta container node-pools create dws-l4-pool \
    --cluster=$CLUSTER_NAME \
    --node-locations $ZONE --region $REGION \
    --enable-queued-provisioning \
    --accelerator type=nvidia-l4,count=1,gpu-driver-version=latest \
    --machine-type=g2-standard-4 \
    --no-enable-autoupgrade \
    --scopes "https://www.googleapis.com/auth/cloud-platform" \
    --enable-autoscaling \
    --num-nodes=0 \
    --total-max-nodes 3 \
    --location-policy=ANY \
    --reservation-affinity=none \
    --no-enable-autorepair