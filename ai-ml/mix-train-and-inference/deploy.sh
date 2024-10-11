#!/bin/sh

# Set up env variables values
# export HF_TOKEN=HF_TOKEN
# export PROJECT_ID=
export REGION=europe-west6
export GPU_POOL_MACHINE_TYPE="g2-standard-24"
export GPU_POOL_ACCELERATOR_TYPE="nvidia-l4"
export TRAINING_DATA_BUCKET="data-bucket-$PROJECT_ID"
export MODEL_BUCKET="model-bucket-$PROJECT_ID"


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
TRAINING_DATA_BUCKET           = "$TRAINING_DATA_BUCKET"
model_bucket                = "$MODEL_BUCKET"
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

sleep 180 # wait for kueue deployment

kubectl apply -f flavors.yaml
kubectl apply -f default-priorityclass.yaml
kubectl apply -f high-priorityclass.yaml
kubectl apply -f low-priorityclass.yaml
kubectl apply -f cluster-queue.yaml

gcloud storage buckets add-iam-policy-binding "gs://$MODEL_BUCKET" \
    --role=roles/storage.objectAdmin \
    --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NAMESPACE/sa/default \
    --condition=None
gcloud storage buckets add-iam-policy-binding "gs://$TRAINING_DATA_BUCKET" \
    --role=roles/storage.objectViewer \
    --member=principal://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$PROJECT_ID.svc.id.goog/subject/ns/$NAMESPACE/sa/default \
    --condition=None


gcloud artifacts repositories add-iam-policy-binding fine-tuning \
    --role=roles/artifactregistry.reader \
    --member=serviceAccount:gke-llm-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --location=$REGION \
    --condition=None


kubectl create -f tgi-gemma-2-9b-it-hp.yaml -n $NAMESPACE
# kubectl apply -f fine-tune-l4-dws.yaml -n $NAMESPACE
sed -e "s/<TRAINING_BUCKET>/$TRAINING_DATA_BUCKET/g" \
-e "s/<MODEL_BUCKET>/$MODEL_BUCKET/g" \
-e "s/<PROJECT_ID>/$PROJECT_ID/g" \
-e "s/<REGION>/$REGION/g" \
fine-tune-l4-dws.yaml |kubectl apply -f - -n $NAMESPACE



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
