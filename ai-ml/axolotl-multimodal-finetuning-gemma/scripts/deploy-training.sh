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
# deploy-training.sh
set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Set variables
export PROJECT_ID=${PROJECT_ID:-$(gcloud config get-value project)}
export GCS_BUCKET_NAME=${GCS_BUCKET_NAME:-${PROJECT_ID}-melanoma-dataset}
export NAMESPACE=${NAMESPACE:-axolotl-training}
export HF_TOKEN=${HF_TOKEN:-}

# Validate required variables
if [ -z "$PROJECT_ID" ]; then
    print_error "PROJECT_ID is not set. Please run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

if [ -z "$HF_TOKEN" ]; then
    print_error "HF_TOKEN is not set. Please export your Hugging Face token:"
    echo "  export HF_TOKEN=your_hugging_face_token"
    echo "  Get a token from: https://huggingface.co/settings/tokens"
    exit 1
fi

print_status "Deploying Axolotl training job"
print_status "Project: ${PROJECT_ID}"
print_status "GCS Bucket: ${GCS_BUCKET_NAME}"
print_status "Namespace: ${NAMESPACE}"

# Check if kubectl is configured
if ! kubectl cluster-info &>/dev/null; then
    print_error "kubectl is not configured. Please run setup-cluster.sh first."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace ${NAMESPACE} &>/dev/null; then
    print_error "Namespace ${NAMESPACE} does not exist. Please run setup-workload-identity.sh first."
    exit 1
fi

# Check if required files exist
REQUIRED_FILES=(
    "k8s/model-storage-pvc.yaml"
    "k8s/axolotl-training-job.yaml"
    "config/gemma3-melanoma.yaml"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        print_error "Required file not found: $file"
        exit 1
    fi
done

# Check if data exists in GCS
print_status "Checking if training data exists in GCS..."
if gsutil ls gs://${GCS_BUCKET_NAME}/axolotl-data/siim_isic_train.jsonl &>/dev/null; then
    print_status "Training data found in GCS"
else
    print_warning "Training data not found at gs://${GCS_BUCKET_NAME}/axolotl-data/siim_isic_train.jsonl"
    print_warning "Please run the DataPreparation notebook to prepare your data"
    read -p "Do you want to continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Apply PersistentVolumeClaim
print_status "Creating PersistentVolumeClaim..."
kubectl apply -f k8s/model-storage-pvc.yaml

# Wait for PVC to be bound
print_status "Waiting for PVC to be bound..."
kubectl wait --for=condition=Bound pvc/model-storage -n ${NAMESPACE} --timeout=60s

# Create or update ConfigMap
print_status "Creating/updating ConfigMap with Axolotl configuration..."
kubectl create configmap axolotl-config \
    --from-file=gemma3-melanoma.yaml=config/gemma3-melanoma.yaml \
    -n ${NAMESPACE} \
    --dry-run=client -o yaml | kubectl apply -f -

# Create or update Hugging Face credentials secret
print_status "Creating/updating Hugging Face credentials..."
kubectl create secret generic huggingface-credentials \
    -n ${NAMESPACE} \
    --from-literal=token=${HF_TOKEN} \
    --dry-run=client -o yaml | kubectl apply -f -

# Check if a training job is already running
if kubectl get job gemma3-melanoma-training -n ${NAMESPACE} &>/dev/null; then
    print_warning "Training job 'gemma3-melanoma-training' already exists"
    JOB_STATUS=$(kubectl get job gemma3-melanoma-training -n ${NAMESPACE} -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}')
    if [ "$JOB_STATUS" == "True" ]; then
        print_info "Previous job completed successfully"
    else
        print_warning "Previous job is still running or failed"
    fi

    read -p "Do you want to delete the existing job and start a new one? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deleting existing job..."
        kubectl delete job gemma3-melanoma-training -n ${NAMESPACE}
        sleep 5
    else
        exit 0
    fi
fi

# Deploy training job with environment variable substitution
print_status "Deploying training job..."
envsubst < k8s/axolotl-training-job.yaml | kubectl apply -f -

# Wait for pod to be created
print_status "Waiting for training pod to be created..."
sleep 10

# Get pod name
POD_NAME=$(kubectl get pods -n ${NAMESPACE} \
    --selector=job-name=gemma3-melanoma-training \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "$POD_NAME" ]; then
    print_error "Training pod not found. Checking job status..."
    kubectl describe job gemma3-melanoma-training -n ${NAMESPACE}
    exit 1
fi

print_status "Training pod created: ${POD_NAME}"

# Deploy TensorBoard (optional)
read -p "Do you want to deploy TensorBoard for monitoring? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Deploying TensorBoard..."
    kubectl apply -f k8s/tensorboard.yaml

    # Wait for TensorBoard to be ready
    print_status "Waiting for TensorBoard deployment..."
    kubectl wait --for=condition=available --timeout=300s \
        deployment/tensorboard -n ${NAMESPACE}

    # Get TensorBoard service IP
    print_status "Getting TensorBoard URL..."
    TB_IP=""
    for i in {1..30}; do
        TB_IP=$(kubectl get service tensorboard -n ${NAMESPACE} \
            -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
        if [ -n "$TB_IP" ]; then
            break
        fi
        sleep 10
    done

    if [ -n "$TB_IP" ]; then
        print_info "TensorBoard available at: http://${TB_IP}"
    else
        print_warning "TensorBoard IP not yet assigned. Check later with:"
        echo "  kubectl get service tensorboard -n ${NAMESPACE}"
    fi
fi

# Monitor training
print_status "Training job deployed successfully!"
print_info "Monitor training progress with:"
echo "  kubectl logs -f ${POD_NAME} -n ${NAMESPACE}"
echo ""
print_info "Check job status with:"
echo "  kubectl get job gemma3-melanoma-training -n ${NAMESPACE}"
echo ""
print_info "Describe pod for debugging:"
echo "  kubectl describe pod ${POD_NAME} -n ${NAMESPACE}"

# Optional: Start following logs
read -p "Do you want to start following the training logs now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    print_status "Following training logs (Ctrl+C to stop)..."
    kubectl logs -f ${POD_NAME} -n ${NAMESPACE}
fi

print_status "Deployment complete!"
