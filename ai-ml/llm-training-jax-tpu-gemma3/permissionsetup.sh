# Copyright 2026 Google LLC
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

#!/bin/bash

# --- Configuration Variables ---
# Kubernetes Service Account details
export KSA_NAME="jaxserviceaccout"
export NAMESPACE="default"

# Google Cloud IAM Service Account details
export GSA_NAME="<GSA_NAME>"
# Automatically get the current project ID
export PROJECT_ID=$(gcloud config get-value project)
export  GSA_DESCRIPTION="GKE Service Account to read GCS bucket for ${KSA_NAME}"

# GCS Bucket details
export GCS_BUCKET_NAME="<GCS_BUCKET_NAME>" # <--- IMPORTANT: Update this to your bucket name

# Derived Variables
export GSA_EMAIL="${GSA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export WI_MEMBER="serviceAccount:${PROJECT_ID}.svc.id.goog[${NAMESPACE}/${KSA_NAME}]"

# --- Check if PROJECT_ID is set ---
if [ -z "${PROJECT_ID}" ]; then
  echo "Error: PROJECT_ID is not set. Please set it using 'gcloud config set project YOUR_PROJECT_ID'"
  exit 1
fi

echo "--- Configuration ---"
echo "KSA_NAME:      ${KSA_NAME}"
echo "NAMESPACE:     ${NAMESPACE}"
echo "GSA_NAME:      ${GSA_NAME}"
echo "PROJECT_ID:    ${PROJECT_ID}"
echo "GSA_EMAIL:     ${GSA_EMAIL}"
echo "GCS_BUCKET_NAME:   ${GCS_BUCKET_NAME}"
echo "WI_MEMBER:     ${WI_MEMBER}"
echo "--------------------"
read -p "Press enter to continue..."

# --- Command Execution ---

echo "[1/5] Creating Google Cloud IAM Service Account (GSA): ${GSA_NAME}"
gcloud iam service-accounts create "${GSA_NAME}" \
    --project="${PROJECT_ID}" \
    --description="${GSA_DESCRIPTION}" \
    --display-name="${GSA_NAME}"

echo "[2/5] Granting GSA '${GSA_EMAIL}' read access (roles/storage.objectViewer) to bucket 'gs://${GCS_BUCKET_NAME}'"
gcloud storage buckets add-iam-policy-binding "gs://${GCS_BUCKET_NAME}" \
    --member="serviceAccount:${GSA_EMAIL}" \
    --role="roles/storage.objectViewer" \
    --project="${PROJECT_ID}"

echo "[3/5] Creating Kubernetes Service Account (KSA): ${KSA_NAME} in namespace ${NAMESPACE}"
kubectl create serviceaccount "${KSA_NAME}" --namespace "${NAMESPACE}"

echo "[4/5] Allowing KSA to impersonate GSA (Workload Identity Binding): ${GSA_EMAIL}"
gcloud iam service-accounts add-iam-policy-binding "${GSA_EMAIL}" \
    --role roles/iam.workloadIdentityUser \
    --member "${WI_MEMBER}" \
    --project="${PROJECT_ID}"

echo "[5/5] Annotating KSA '${KSA_NAME}' to link with GSA '${GSA_EMAIL}'"
kubectl annotate serviceaccount "${KSA_NAME}" \
    --namespace "${NAMESPACE}" \
    iam.gke.io/gcp-service-account="${GSA_EMAIL}"

echo "--- Setup Complete ---"
echo "Pods in namespace '${NAMESPACE}' using serviceAccount '${KSA_NAME}' can now authenticate as '${GSA_EMAIL}' and have read access to 'gs://${GCS_BUCKET_NAME}'."
