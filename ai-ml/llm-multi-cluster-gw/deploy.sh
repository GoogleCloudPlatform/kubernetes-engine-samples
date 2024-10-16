#!/bin/sh

# Set up env variables values
# export HF_TOKEN=HF_TOKEN
# export REGION_1=us-central1
# export REGION_2=europe-west4
# export GPU_POOL_MACHINE_TYPE_1="a2-highgpu-1g"
# export GPU_POOL_ACCELERATOR_TYPE_1="nvidia-tesla-a100"
# export GPU_POOL_MACHINE_TYPE_2="g2-standard-4"
# export GPU_POOL_ACCELERATOR_TYPE_2="nvidia-l4"
set -e

PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud services enable container.googleapis.com \
    --project=$PROJECT_ID 

# Create terraform.tfvars file 
cat <<EOF >gke-platform/terraform.tfvars
project_id                  = "$PROJECT_ID"
enable_autopilot            = true
region_1                    = "$REGION_1"
region_2                    = "$REGION_2"
gpu_pool_machine_type_1     = "$GPU_POOL_MACHINE_TYPE_1"
gpu_pool_accelerator_type_1 = "$GPU_POOL_ACCELERATOR_TYPE_1"
gpu_pool_machine_type_2     = "$GPU_POOL_MACHINE_TYPE_2"
gpu_pool_accelerator_type_2 = "$GPU_POOL_ACCELERATOR_TYPE_2"
gpu_pool_node_locations_1   = $(gcloud compute accelerator-types list --filter="zone ~ $REGION_1 AND name=$GPU_POOL_ACCELERATOR_TYPE_1" --limit=2 --format=json | jq -sr 'map(.[].zone|split("/")|.[8])|tojson')
gpu_pool_node_locations_2   = $(gcloud compute accelerator-types list --filter="zone ~ $REGION_2 AND name=$GPU_POOL_ACCELERATOR_TYPE_2" --limit=2 --format=json | jq -sr 'map(.[].zone|split("/")|.[8])|tojson')
fleet_project_id            = "$PROJECT_ID"
enable_fleet                = true
gateway_api_channel         = "CHANNEL_STANDARD"
EOF

# Create clusters
terraform -chdir=gke-platform init
terraform -chdir=gke-platform apply

set +e
# Get cluster credentials
gcloud container clusters get-credentials llm-cluster-1 \
    --region=$REGION_1 \
    --project=$PROJECT_ID

gcloud container clusters get-credentials llm-cluster-2 \
    --region=$REGION_2 \
    --project=$PROJECT_ID

# Rename cluster contexts
kubectl config rename-context gke_${PROJECT_ID}_us-central1_llm-cluster-1 gke-us
kubectl config rename-context gke_${PROJECT_ID}_europe-west4_llm-cluster-2 gke-eu

# Enable multi-cluster Services in the fleet
gcloud container fleet multi-cluster-services enable \
    --project $PROJECT_ID

#Grant Identity and Access Management (IAM) permissions required by the MCS controller
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member "serviceAccount:$PROJECT_ID.svc.id.goog[gke-mcs/gke-mcs-importer]" \
    --role "roles/compute.networkViewer" \
    --condition=None \
    --project=$PROJECT_ID


# Enable multi-cluster Gateway in the fleet, choose lm-cluster-1 cluster as config cluster
gcloud container fleet ingress enable \
    --config-membership=projects/$PROJECT_ID/locations/$REGION_1/memberships/llm-cluster-1 \
    --project=$PROJECT_ID
# Add second cluster
gcloud container fleet ingress update \
    --config-membership=projects/$PROJECT_ID/locations/$REGION_2/memberships/llm-cluster-2 \
    --project=$PROJECT_ID


# Grant Identity and Access Management (IAM) permissions required by the multi-cluster Gateway controller
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member "serviceAccount:service-$PROJECT_NUMBER@gcp-sa-multiclusteringress.iam.gserviceaccount.com" \
    --role "roles/container.admin" \
    --condition=None \
    --project=$PROJECT_ID


NAMESPACE=llm

# Deploy workloads in gke-us
kubectl config use-context gke-us
kubectl create ns $NAMESPACE
kubectl create secret generic hf-secret \
--from-literal=hf_api_token=$HF_TOKEN \
--dry-run=client -o yaml | kubectl apply --context=gke-us -n $NAMESPACE -f -

sed -e "s/GPU_ACCELERATOR_TYPE/$GPU_POOL_ACCELERATOR_TYPE_1/g" tgi-2b-it-1.1.yaml |kubectl apply -f - -n $NAMESPACE

# Deploy serviceExport 
kubectl apply -f export-us.yaml -n $NAMESPACE

# Deploy workloads in gke-eu
kubectl config use-context gke-eu
kubectl create ns  $NAMESPACE
kubectl create secret generic hf-secret \
--from-literal=hf_api_token=$HF_TOKEN \
--dry-run=client -o yaml | kubectl apply --context=gke-eu -n $NAMESPACE -f -

sed -e "s/GPU_ACCELERATOR_TYPE/$GPU_POOL_ACCELERATOR_TYPE_2/g" tgi-2b-it-1.1.yaml |kubectl apply -f - -n $NAMESPACE

# Deploy serviceExport 
kubectl apply -f export-eu.yaml -n $NAMESPACE

# Deploy multicluster gateway in config cluster 

kubectl apply -f gateway.yaml -n $NAMESPACE --context=gke-us
kubectl apply -f gateway.yaml -n $NAMESPACE --context=gke-eu

sleep 360 # wait for monitoring 
kubectl apply -f monitoring.yaml -n $NAMESPACE --context=gke-us
kubectl apply -f monitoring.yaml -n $NAMESPACE --context=gke-eu

#Grant your user the ability to create required authorization roles:
kubectl create clusterrolebinding cluster-admin-binding \
    --clusterrole cluster-admin --user "$(gcloud config get-value account)"

#Deploy the custom metrics adapter on your cluster:
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter_new_resource_model.yaml --context=gke-eu
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/k8s-stackdriver/master/custom-metrics-stackdriver-adapter/deploy/production/adapter_new_resource_model.yaml --context=gke-us

gcloud projects add-iam-policy-binding projects/$PROJECT_ID \
  --role roles/monitoring.viewer \
  --condition=None \
  --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/custom-metrics/sa/custom-metrics-stackdriver-adapter

kubectl apply -f hpa-custom-metrics.yaml -n llm --context=gke-us 
kubectl apply -f hpa-custom-metrics.yaml -n llm --context=gke-eu