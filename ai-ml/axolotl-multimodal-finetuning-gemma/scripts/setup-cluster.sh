# Copyright 2025 Google LLC
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

#!/bin/bash
# setup-cluster.sh
set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Set default values
export PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
export REGION=${REGION:-us-central1}
export CLUSTER_NAME=${CLUSTER_NAME:-melanoma-training-cluster}
export RELEASE_CHANNEL=${RELEASE_CHANNEL:-regular}
export GCS_BUCKET_NAME=${GCS_BUCKET_NAME:-${PROJECT_ID}-melanoma-dataset}

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    print_error "PROJECT_ID is not set. Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

print_status "Starting GKE cluster setup for project: ${PROJECT_ID}"
print_status "Region: ${REGION}"
print_status "Cluster name: ${CLUSTER_NAME}"
print_status "GCS bucket: ${GCS_BUCKET_NAME}"

# Enable required Google APIs
print_status "Enabling required Google APIs..."
gcloud services enable container.googleapis.com --project=${PROJECT_ID}
gcloud services enable compute.googleapis.com --project=${PROJECT_ID}
gcloud services enable storagetransfer.googleapis.com --project=${PROJECT_ID}
gcloud services enable artifactregistry.googleapis.com --project=${PROJECT_ID}

# Wait for API enablement to propagate
print_status "Waiting for API enablement to propagate..."
sleep 10

# Check if cluster already exists
if gcloud container clusters describe ${CLUSTER_NAME} --location=${REGION} --project=${PROJECT_ID} &>/dev/null; then
    print_warning "Cluster ${CLUSTER_NAME} already exists in ${REGION}"
    read -p "Do you want to get credentials for the existing cluster? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Getting credentials for existing cluster..."
        gcloud container clusters get-credentials ${CLUSTER_NAME} \
            --location=${REGION} \
            --project=${PROJECT_ID}
    fi
else
    # Create GKE Autopilot cluster
    print_status "Creating GKE Autopilot cluster ${CLUSTER_NAME}..."
    gcloud container clusters create-auto ${CLUSTER_NAME} \
        --location=${REGION} \
        --project=${PROJECT_ID} \
        --release-channel=${RELEASE_CHANNEL} \
        --enable-autoscaling \
        --enable-autorepair \
        --enable-autoupgrade

    # Get cluster credentials
    print_status "Getting cluster credentials..."
    gcloud container clusters get-credentials ${CLUSTER_NAME} \
        --location=${REGION} \
        --project=${PROJECT_ID}
fi

# Install kubectl if not already installed
if ! command -v kubectl &> /dev/null; then
    print_status "Installing kubectl..."
    gcloud components install kubectl
fi

# Install GKE auth plugin
print_status "Installing/updating GKE auth plugin..."
gcloud components install gke-gcloud-auth-plugin

# Verify kubectl connection
print_status "Verifying kubectl connection to cluster..."
if kubectl cluster-info &>/dev/null; then
    print_status "Successfully connected to cluster"
    kubectl get nodes
else
    print_error "Failed to connect to cluster"
    exit 1
fi

# Create GCS bucket if it doesn't exist
if ! gsutil ls -b gs://${GCS_BUCKET_NAME} &>/dev/null; then
    print_status "Creating GCS bucket: gs://${GCS_BUCKET_NAME}"
    gcloud storage buckets create gs://${GCS_BUCKET_NAME} \
        --location=${REGION} \
        --uniform-bucket-level-access \
        --project=${PROJECT_ID}
else
    print_warning "GCS bucket gs://${GCS_BUCKET_NAME} already exists"
fi

# Set up Storage Transfer Service permissions
print_status "Setting up Storage Transfer Service permissions..."
export PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")
export STS_SERVICE_ACCOUNT="project-${PROJECT_NUMBER}@storage-transfer-service.iam.gserviceaccount.com"

# Grant permissions to Storage Transfer Service
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET_NAME} \
    --member=serviceAccount:${STS_SERVICE_ACCOUNT} \
    --role=roles/storage.objectViewer \
    --condition=None 2>/dev/null || print_warning "Storage Transfer viewer role may already be set"

gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET_NAME} \
    --member=serviceAccount:${STS_SERVICE_ACCOUNT} \
    --role=roles/storage.objectUser \
    --condition=None 2>/dev/null || print_warning "Storage Transfer user role may already be set"

# Check GPU quota
print_status "Checking GPU quota in region ${REGION}..."
GPU_QUOTA=$(gcloud compute project-info describe --project=${PROJECT_ID} \
    --format="value(quotas[name='NVIDIA_A100_GPUS'].limit)" 2>/dev/null || echo "0")

if [ "$GPU_QUOTA" == "0" ] || [ -z "$GPU_QUOTA" ]; then
    print_warning "No A100 GPU quota found in project. You may need to request quota increase."
    print_warning "Visit: https://console.cloud.google.com/iam-admin/quotas"
fi

print_status "Cluster setup complete!"
print_status "Next steps:"
echo "  1. Run ./scripts/setup-workload-identity.sh to configure Workload Identity"
echo "  2. Prepare your data using the DataPreparation notebook"
echo "  3. Run ./scripts/deploy-training.sh to start training"
