# Ensure that the project_id is set
gcloud config set project PROJECT_ID

# Set the required environment variables
export PROJECT_ID=$(gcloud config get project) \
&& export PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT_ID" --format="value(PROJECT_NUMBER)") \
&& export REGION=REGION \
&& export ZONE=ZONE \
&& export CLUSTER_NAME=CLUSTER_NAME \
&& export BUCKET_NAME=MODEL_FILES_BUCKET_NAME \
&& export KSA_NAME=K8S_SERVICE_ACCOUNT_NAME \
&& export MODEL_PATH=MODEL_PATH_NAME \
&& export ROLE_NAME=ROLE_NAME \
&& export DISK_IMAGE=DISK_IMAGE_NAME \
&& export LOG_BUCKET_NAME=$BUCKET_NAME-disk-creation-logs \
&& export CONTAINER_IMAGE=CONTAINER_IMAGE_NAME

# Add the Hugging Face username and Hugging Face user token to the cloud secrets
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


# Run the Cloud Build command to prepare the cluster with all required substitutions
gcloud builds submit \
  --config cloudbuild-prepare.yaml --no-source \
  --substitutions=_DISK_IMAGE=$DISK_IMAGE,_CONTAINER_IMAGE=$CONTAINER_IMAGE,_BUCKET_NAME=$LOG_BUCKET_NAME,_REGION=$REGION,_ZONE=$ZONE,_CLUSTER_NAME=$CLUSTER_NAME,_PROJECT_ID=$PROJECT_ID

# Run the Cloud Build command for model weights prelod with all required substitutions
gcloud builds submit \
  --config cloudbuild-preload.yaml \
  --substitutions=_BUCKET_NAME=$BUCKET_NAME,_CLUSTER_NAME=$CLUSTER_NAME,_REGION=$REGION,_KSA_NAME=$KSA_NAME,_PROJECT_NUMBER=$PROJECT_NUMBER,_PROJECT_ID=$PROJECT_ID,_ROLE_NAME=$ROLE_NAME,_MODEL_PATH=$MODEL_PATH

# Check if files are downloaded to the Cloud Storage bucket
gsutil ls gs://$BUCKET_NAME/$MODEL_PATH

# Setup the kubectl
gcloud container clusters get-credentials ${CLUSTER_NAME} \
  --location=${REGION}

# Apply the manifest and change the placeholder with the name of the requred bucket and required k8s service account in STANDARD
sed "s|<BUCKET_NAME>|$BUCKET_NAME|g; s|<KSA_NAME>|$KSA_NAME|g; s|<CONTAINER_IMAGE>|'$CONTAINER_IMAGE'|g" model-deployment.yaml | kubectl apply -f -

# Clean-up
gcloud secrets delete hf-username \
  --quiet \
&& gcloud secrets delete hf-token \
    --quiet \
&& gcloud container clusters delete ${CLUSTER_NAME} \
    --region=${REGION} \
    --quiet \
&& gcloud projects remove-iam-policy-binding $PROJECT_ID \
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
    --condition=None \
&& gsutil -m rm -rf gs://$BUCKET_NAME \
&& gsutil -m rm -rf gs://$LOG_BUCKET_NAME \
&& gcloud compute images delete $DISK_IMAGE \
    --quiet
