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
# setup-workload-identity.sh
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

# Set variables
export PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
export NAMESPACE=${NAMESPACE:-axolotl-training}
export KSA_NAME=${KSA_NAME:-axolotl-training-sa}
export GSA_NAME=${GSA_NAME:-axolotl-training-sa}
export GCS_BUCKET_NAME=${GCS_BUCKET_NAME:-${PROJECT_ID}-melanoma-dataset}

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    print_error "PROJECT_ID is not set. Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

print_status "Setting up Workload Identity Federation"
print_status "Project: ${PROJECT_ID}"
print_status "Namespace: ${NAMESPACE}"
print_status "Service Accounts: ${KSA_NAME} (K8s) / ${GSA_NAME} (Google)"

# Check if kubectl is configured
if ! kubectl cluster-info &>/dev/null; then
    print_error "kubectl is not configured. Please run setup-cluster.sh first."
    exit 1
fi

# Create Kubernetes namespace
if kubectl get namespace ${NAMESPACE} &>/dev/null; then
    print_warning "Namespace ${NAMESPACE} already exists"
else
    print_status "Creating namespace ${NAMESPACE}..."
    kubectl create namespace ${NAMESPACE}
fi

# Create Kubernetes ServiceAccount
if kubectl get serviceaccount ${KSA_NAME} -n ${NAMESPACE} &>/dev/null; then
    print_warning "Kubernetes ServiceAccount ${KSA_NAME} already exists"
else
    print_status "Creating Kubernetes ServiceAccount ${KSA_NAME}..."
    kubectl create serviceaccount ${KSA_NAME} --namespace=${NAMESPACE}
fi

# Create Google Service Account
if gcloud iam service-accounts describe ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com &>/dev/null; then
    print_warning "Google Service Account ${GSA_NAME} already exists"
else
    print_status "Creating Google Service Account ${GSA_NAME}..."
    gcloud iam service-accounts create ${GSA_NAME} \
        --display-name="Axolotl Training Service Account" \
        --description="Service account for Axolotl multimodal fine-tuning on GKE" \
        --project=${PROJECT_ID}

    # Wait for IAM propagation
    print_status "Waiting for IAM service account creation to propagate..."
    sleep 15
fi

# Grant necessary permissions to the Google Service Account
print_status "Granting storage.objectAdmin role to Google Service Account..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --condition=None

# Additional role for GCS FUSE
print_status "Granting storage.admin role for GCS FUSE operations..."
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
    --member="serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.admin" \
    --condition=None

# Grant bucket-specific permissions
print_status "Granting bucket-specific permissions..."
gcloud storage buckets add-iam-policy-binding gs://${GCS_BUCKET_NAME} \
    --member="serviceAccount:${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" \
    --condition=None

# Wait for IAM propagation
print_status "Waiting for IAM policy bindings to propagate..."
sleep 10

# Enable Workload Identity binding
print_status "Binding Kubernetes ServiceAccount to Google Service Account..."
gcloud iam service-accounts add-iam-policy-binding \
    ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --role="roles/iam.workloadIdentityUser" \
    --member="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]" \
    --project=${PROJECT_ID}

# Annotate Kubernetes ServiceAccount
print_status "Annotating Kubernetes ServiceAccount..."
kubectl annotate serviceaccount ${KSA_NAME} \
    --namespace=${NAMESPACE} \
    iam.gke.io/gcp-service-account=${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
    --overwrite

# Verify the setup
print_status "Verifying Workload Identity setup..."
kubectl get serviceaccount ${KSA_NAME} -n ${NAMESPACE} -o yaml | grep -A 1 "annotations:"

# Test Workload Identity
print_status "Testing Workload Identity authentication..."
kubectl run -it --rm workload-identity-test \
    --image=google/cloud-sdk:slim \
    --serviceaccount=${KSA_NAME} \
    --namespace=${NAMESPACE} \
    --restart=Never \
    --command -- /bin/bash -c "
        echo 'Testing authentication...'
        if gcloud auth list 2>/dev/null | grep -q ${GSA_NAME}; then
            echo 'SUCCESS: Authenticated as ${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com'
            echo 'Testing GCS access...'
            if gsutil ls gs://${GCS_BUCKET_NAME}/ >/dev/null 2>&1; then
                echo 'SUCCESS: Can access GCS bucket'
            else
                echo 'ERROR: Cannot access GCS bucket'
                exit 1
            fi
        else
            echo 'ERROR: Not authenticated correctly'
            exit 1
        fi
    "

if [ $? -eq 0 ]; then
    print_status "Workload Identity setup completed successfully!"
else
    print_error "Workload Identity test failed. Please check the configuration."
    exit 1
fi

print_status "Next steps:"
echo "  1. Prepare your data using the DataPreparation notebook"
echo "  2. Run ./scripts/deploy-training.sh to start training"

