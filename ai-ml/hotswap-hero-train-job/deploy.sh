#!/bin/sh

# Set up env variables values

# export PROJECT_ID=

export REGION=us-west4
export TPU_NODE_LOCATION=us-west4-a


PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud services enable container.googleapis.com \
    --project=$PROJECT_ID 

# Create terraform.tfvars file 
cat <<EOF >gke-platform/terraform.tfvars
project_id                  = "$PROJECT_ID"
enable_autopilot            = false
enable_tpu                  = true
region                      = "$REGION"
tpu_node_location           = ["$TPU_NODE_LOCATION"]
tpu_machine_type            = "ct5lp-hightpu-4t"
tpu_topology                 = "2x4"
tpu_node_pools_number       = 3
EOF

# Create clusters
terraform -chdir=gke-platform init 
terraform -chdir=gke-platform apply 

# Get cluster credentials
gcloud container clusters get-credentials llm-cluster \
    --region=$REGION \
    --project=$PROJECT_ID

# Install JobSets
kubectl apply --server-side -f https://github.com/kubernetes-sigs/jobset/releases/download/v0.7.0/manifests.yaml

sleep 60 # wait for jobset to install
kubectl create -f workloads/priority.yaml

kubectl create -f workloads/high-priority-job.yaml
kubectl create -f workloads/low-priority-job.yaml


