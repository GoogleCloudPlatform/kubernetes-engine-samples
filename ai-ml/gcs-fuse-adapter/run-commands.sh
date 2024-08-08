# Ensure that the project_id is set
gcloud config set project PROJECT_ID

# Set the required environment variables
export PROJECT_ID=$(gcloud config get project) \
&& export PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT_ID" --format="value(PROJECT_NUMBER)") \
&& export REGION=REGION \
&& export ZONE=$REGION-a \
&& export CLUSTER_NAME=CLUSTER_NAME \
&& export NODEPOOL_NAME=NODEPOOL_NAME \
&& export BUCKET_NAME=gs://MODEL_FILES_BUCKET_NAME/ \
&& export KSA_NAME=K8S_SERVICE_ACCOUNT_NAME \
&& export MODEL_PATH=MODEL_PATH_NAME \
&& export ROLE_NAME=ROLE_NAME

# Add the Hugging Face username and Hugging Face user token to the cloud secrets
echo -n 'YOUR_HUGGINGFACE_USER_NAME' | gcloud secrets create hf-username --data-file=-
echo -n 'YOUR_HUGGINGFACE_USER_TOKEN' | gcloud secrets create hf-token --data-file=-

# Create a GKE Autopilot cluster
gcloud container clusters create-auto ${CLUSTER_NAME} \
  --project=${PROJECT_ID} \
  --region=${REGION} \
  --release-channel=rapid \
  --cluster-version=1.28

# Create a GKE Standard cluster
gcloud container clusters create ${CLUSTER_NAME} \
  --project=${PROJECT_ID} \
  --region=${REGION} \
  --workload-pool=${PROJECT_ID}.svc.id.goog \
  --release-channel=rapid \
  --cluster-version=1.28 \
  --num-nodes=1 \
  --addons GcsFuseCsiDriver

# Create a node pool
gcloud container node-pools create ${NODEPOOL_NAME} \
  --accelerator type=nvidia-l4,count=2,gpu-driver-version=latest \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --node-locations=${REGION}-a \
  --cluster=${CLUSTER_NAME} \
  --machine-type=g2-standard-24 \
  --num-nodes=1

# Add the required permissions to the default Cloud Build service account
gcloud projects add-iam-policy-binding projects/$PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/storage.admin" \
    --condition=None

# Run the Cloud Build command with all required substitutions
gcloud builds submit \
  --config cloudbuild.yaml \
--substitutions=_BUCKET_NAME=$BUCKET_NAME,_CLUSTER_NAME=$CLUSTER_NAME,_REGION=$REGION,_KSA_NAME=$KSA_NAME,_PROJECT_NUMBER=$PROJECT_NUMBER,_PROJECT_ID=$PROJECT_ID,_ROLE_NAME=$ROLE_NAME,_MODEL_PATH=$MODEL_PATH 

# Check if files are downloaded to the Cloud Storage bucket
gsutil ls gs://$BUCKET_NAME/$MODEL_PATH

# Apply the manifest and change the placeholder with the name of the requred bucket
sed "s|<BUCKET_NAME>|$BUCKET_NAME|" model-deployment.yaml | kubectl apply -f -

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
&& gsutil -m rm -rf gs://$BUCKET_NAME