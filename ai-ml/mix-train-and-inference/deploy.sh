#!/bin/sh
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Set up env variables values
# export HF_TOKEN=HF_TOKEN
# export PROJECT_ID=
export REGION=europe-west6
export GPU_POOL_MACHINE_TYPE="g2-standard-24"
export GPU_POOL_ACCELERATOR_TYPE="nvidia-l4"
export TRAINING_DATA_BUCKET="data-bucket-$PROJECT_ID"
export MODEL_BUCKET="model-bucket-$PROJECT_ID"

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud services enable container.googleapis.com \
    --project=$PROJECT_ID 

# Create terraform.tfvars file 
cat <<EOF >gke-platform/terraform.tfvars
project_id                  = "$PROJECT_ID"
enable_autopilot            = true
region                      = "$REGION"
gpu_pool_machine_type       = "$GPU_POOL_MACHINE_TYPE"
gpu_pool_accelerator_type   = "$GPU_POOL_ACCELERATOR_TYPE"
gpu_pool_node_locations     = $(gcloud compute accelerator-types list --filter="zone ~ $REGION AND name=$GPU_POOL_ACCELERATOR_TYPE" --limit=2 --format=json | jq -sr 'map(.[].zone|split("/")|.[8])|tojson')

enable_fleet                = false
gateway_api_channel         = "CHANNEL_STANDARD"
training_data_bucket        = "$TRAINING_DATA_BUCKET"
model_bucket                = "$MODEL_BUCKET"
EOF

# Create clusters
terraform -chdir=gke-platform init 
terraform -chdir=gke-platform apply 

# Get cluster credentials
gcloud container clusters get-credentials llm-cluster \
    --region=$REGION \
    --project=$PROJECT_ID

# upload training dataset to bucket
gcloud storage rsync -r training_data/ gs://$TRAINING_DATA_BUCKET/

NAMESPACE=llm

kubectl create ns $NAMESPACE
kubectl create secret generic hf-secret \
--from-literal=hf_api_token=$HF_TOKEN \
--dry-run=client -o yaml | kubectl apply -n $NAMESPACE -f -

# kubectl apply --server-side -f manifests.yaml
kubectl kustomize kueue/ |kubectl apply --server-side -f - 

sleep 180 # wait for kueue deployment

cd workloads
kubectl apply -f flavors.yaml
kubectl apply -f default-priorityclass.yaml
kubectl apply -f high-priorityclass.yaml
kubectl apply -f low-priorityclass.yaml
kubectl apply -f cluster-queue.yaml
kubectl apply -f local-queue.yaml -n $NAMESPACE

gcloud storage buckets add-iam-policy-binding "gs://$MODEL_BUCKET" \
    --role=roles/storage.objectAdmin \
    --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NAMESPACE/sa/default \
    --condition=None
gcloud storage buckets add-iam-policy-binding "gs://$TRAINING_DATA_BUCKET" \
    --role=roles/storage.objectViewer \
    --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NAMESPACE/sa/default \
    --condition=None

kubectl create -f tgi-gemma-2-9b-it-hp.yaml -n $NAMESPACE

# deploy fine-tuning job
sed -e "s/<TRAINING_BUCKET>/$TRAINING_DATA_BUCKET/g" \
-e "s/<MODEL_BUCKET>/$MODEL_BUCKET/g" \
fine-tune-l4.yaml |kubectl apply -f - -n $NAMESPACE
