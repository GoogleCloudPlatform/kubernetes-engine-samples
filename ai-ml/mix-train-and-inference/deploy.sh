#!/bin/sh

# Set up env variables values
# export HF_TOKEN=HF_TOKEN
# export PROJECT_ID=
export REGION=europe-west4
export GPU_POOL_MACHINE_TYPE="g2-standard-4"
export GPU_POOL_ACCELERATOR_TYPE="nvidia-l4"
 



gcloud services enable container.googleapis.com \
    --project=$PROJECT_ID 

# Create terraform.tfvars file 
cat <<EOF >gke-platform/terraform.tfvars
project_id                  = "$PROJECT_ID"
enable_autopilot            = false
region                      = "$REGION"
gpu_pool_machine_type       = "$GPU_POOL_MACHINE_TYPE"
gpu_pool_accelerator_type   = "$GPU_POOL_ACCELERATOR_TYPE"
gpu_pool_node_locations     = $(gcloud compute accelerator-types list --filter="zone ~ $REGION AND name=$GPU_POOL_ACCELERATOR_TYPE" --limit=2 --format=json | jq -sr 'map(.[].zone|split("/")|.[8])|tojson')

enable_fleet                = false
gateway_api_channel         = "CHANNEL_STANDARD"
EOF

# Create clusters
terraform -chdir=gke-platform init 
terraform -chdir=gke-platform apply 

# Get cluster credentials
gcloud container clusters get-credentials llm-cluster \
    --region=$REGION \
    --project=$PROJECT_ID


NAMESPACE=llm
cd workloads
kubectl create ns $NAMESPACE
kubectl create secret generic hf-secret \
--from-literal=hf_api_token=$HF_TOKEN \
--dry-run=client -o yaml | kubectl apply -n $NAMESPACE -f -

kubectl apply --server-side -f manifests.yaml

sleep 60
kubectl apply -f flavors.yaml
kubectl apply -f default-priorityclass.yaml
kubectl apply -f high-priorityclass.yaml
kubectl apply -f cluster-queue.yaml

kubectl create -f tgi-2b-it-1.1.yaml -n $NAMESPACE


# sleep 360
# kubectl apply -f monitoring.yaml -n $NAMESPACE

# #Grant your user the ability to create required authorization roles:
# kubectl create clusterrolebinding cluster-admin-binding \
#     --clusterrole cluster-admin --user "$(gcloud config get-value account)"

# #Deploy the custom metrics adapter on your cluster:
# kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter_new_resource_model.yaml

# gcloud projects add-iam-policy-binding projects/$PROJECT_ID \
#   --role roles/monitoring.viewer \
#   --condition=None \
#   --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/custom-metrics/sa/custom-metrics-stackdriver-adapter

# kubectl apply -f hpa-custom-metrics.yaml -n llm 
