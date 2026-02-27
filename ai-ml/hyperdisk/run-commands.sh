# Copyright 2024 Google LLC
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

# Ensure that the project_id is set
gcloud config set project PROJECT_ID

# Set the required environment variables
export PROJECT_ID=$(gcloud config get project) \
&& export PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT_ID" --format="value(PROJECT_NUMBER)") \
&& export REGION=europe-west4 \
&& export CLUSTER_NAME=CLUSTER_NAME \
&& export DISK_IMAGE=DISK_IMAGE_NAME \
&& export LOG_BUCKET_NAME=$LOG_BUCKET_NAME \
&& export CONTAINER_IMAGE=CONTAINER_IMAGE_NAME \
&& export HF_TOKEN=HF_TOKEN \
&& for zone in A B C … ; do export ZONE_$zone="$REGION-$(echo $zone | tr A-Z a-z)"; done


echo -n ${HF_USERNAME} | gcloud secrets create hf-username --data-file=- \
&& echo -n ${HF_TOKEN} | gcloud secrets create hf-token --data-file=-

# Add the required permissions to the default Cloud Build service account
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/storage.admin" \
    --condition=None \
&& gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None \
&& gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/container.clusterAdmin" \
    --condition=None \
&& gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/compute.instanceAdmin.v1" \
    --condition=None


# Run the Cloud Build command to prepare the AUTOPILOT cluster with all required substitutions
gcloud builds submit \
  --config cloudbuild-prepare-autopilot.yaml --no-source \
  --substitutions=_DISK_IMAGE=$DISK_IMAGE,_CONTAINER_IMAGE=$CONTAINER_IMAGE,_BUCKET_NAME=$LOG_BUCKET_NAME,_REGION=$REGION,_ZONE_A=$ZONE_A,_CLUSTER_NAME=$CLUSTER_NAME,_PROJECT_ID=$PROJECT_ID

# Run the Cloud Build command to prepare the STANDARD cluster with all required substitutions
gcloud builds submit \
  --config cloudbuild-prepare-standard.yaml --no-source \
  --substitutions=_DISK_IMAGE=$DISK_IMAGE,_CONTAINER_IMAGE=$CONTAINER_IMAGE,_BUCKET_NAME=$LOG_BUCKET_NAME,_REGION=$REGION,_ZONE_A=$ZONE_A,_ZONE_B=$ZONE_B,_ZONE_C=$ZONE_C,_CLUSTER_NAME=$CLUSTER_NAME,_PROJECT_ID=$PROJECT_ID

# Run the Cloud Build command to preload model files to the HDML and apply all the required manifests. (AUTOPILOT)
gcloud builds submit \
  --config cloudbuild-preload-apply.yaml --no-source \
  --substitutions=_REGION=$REGION,_CLUSTER_NAME=$CLUSTER_NAME,_HF_TOKEN=$HF_TOKEN,_DISK_IMAGE=$DISK_IMAGE,_PROJECT_ID=$PROJECT_ID,_CLUSTER_TYPE=autopilot

# Run the Cloud Build command to preload model files to the HDML and apply all the required manifests. (STANDARD)
gcloud builds submit \
  --config cloudbuild-preload-apply.yaml --no-source \
  --substitutions=_REGION=$REGION,_CLUSTER_NAME=$CLUSTER_NAME,_HF_TOKEN=$HF_TOKEN,_CLUSTER_TYPE=standard

# Check the logs of the pod
kubectl logs $(kubectl get pods -o jsonpath='{.items[0].metadata.name}')

# Clean-up
gcloud builds submit \
  --config cloudbuild-cleanup.yaml --no-source \
  --substitutions=_CLUSTER_NAME=$CLUSTER_NAME,_REGION=$REGION,_BUCKET_NAME=$LOG_BUCKET_NAME,_DISK_IMAGE=$DISK_IMAGE

# Remove permisions
gcloud projects remove-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/storage.admin" \
    --condition=None \
&& gcloud projects remove-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None \
&& gcloud projects remove-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/container.clusterAdmin" \
    --condition=None \
&& gcloud projects remove-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/compute.instanceAdmin.v1" \
    --condition=None
