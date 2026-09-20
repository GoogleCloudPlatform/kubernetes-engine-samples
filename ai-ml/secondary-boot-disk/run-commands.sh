# Ensure that the project_id is set
gcloud config set project PROJECT_ID

# Set the required environment variables
export PROJECT_ID=$(gcloud config get project) \
&& export PROJECT_NUMBER=$(gcloud projects list --filter="$PROJECT_ID" --format="value(PROJECT_NUMBER)") \
&& export REGION=REGION \
&& export ZONE=$REGION-a \
&& export REPOSITORY_NAME=AR_REPOSITORY_NAME \
&& export MODEL_PATH=MODEL_PATH_NAME \
&& export IMAGE_NAME=$MODEL_PATH-container-image\
&& export IMAGE_TAG=IMAGE_VERSION_TAG \
&& export DISK_IMAGE=$MODEL_PATH-disk-image\
&& export CONTAINER_IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY_NAME/$IMAGE_NAME:$IMAGE_TAG \
&& export BUCKET_NAME=gs://BUCKET_FOR_LOGS_NAME/ \
&& export CLUSTER_NAME=CLUSTER_NAME

# Add the Hugging Face username and Hugging Face user token to the cloud secrets
echo -n 'YOUR_HUGGINGFACE_USER_NAME' | gcloud secrets create hf-username --data-file=- \
&& echo -n 'YOUR_HUGGINGFACE_USER_TOKEN' | gcloud secrets create hf-token --data-file=-

# create a repository in the artifact registr
gcloud artifacts repositories create $REPOSITORY_NAME \
  --repository-format=docker \
  --location=$REGION \
  --description="repository to store the container images with the preloaded model weights and the configuration files"

# Add the required permissions to the default Cloud Build service account
gcloud projects add-iam-policy-binding projects/$PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/compute.instanceAdmin.v1" \
    --role="roles/iam.serviceAccountUser" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None

# Run the Cloud Build command with substitutions
gcloud builds submit \
  --config cloudbuild-image.yaml \
--substitutions=_MODEL_PATH=$MODEL_PATH,_PROJECT_ID=$PROJECT_ID,_REPOSITORY_NAME=$REPOSITORY_NAME,_IMAGE_NAME=$IMAGE_NAME,_REGION=$REGION,_IMAGE_TAG=$IMAGE_TAG

# Check the existing container image
gcloud artifacts docker images list $REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY_NAME

# Run the Cloud Build command with substitutions
gcloud builds submit --config cloudbuild-disk.yaml --no-source \
--substitutions=_DISK_IMAGE=$DISK_IMAGE,_CONTAINER_IMAGE=$CONTAINER_IMAGE,_BUCKET_NAME=$BUCKET_NAME,_REGION=$REGION,_ZONE=$ZONE

# check the existing disk image
gcloud compute images list --no-standard-images

# Create a GKE Standard cluster
gcloud container clusters create ${CLUSTER_NAME} \
  --project=${PROJECT_ID} \
  --region=${REGION} \
  --workload-pool=${PROJECT_ID}.svc.id.goog \
  --release-channel=rapid \
  --cluster-version=1.28 \
  --num-nodes=1 \
  --enable-image-streaming

# Create a node pool with a secondary boot disk
gcloud beta container node-pools create gpupool \
  --accelerator type=nvidia-l4,count=2,gpu-driver-version=latest \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --node-locations=${ZONE} \
  --cluster=${CLUSTER_NAME} \
  --machine-type=g2-standard-24 \
  --num-nodes=1 \
  --disk-size 200 \
  --enable-image-streaming \
 --secondary-boot-disk=disk-image=projects/${PROJECT_ID}/global/images/${DISK_IMAGE},mode=CONTAINER_IMAGE_CACHE

# Apply the deployment and change the placeholder with the name of the container image
sed "s|<CONTAINER_IMAGE>|$CONTAINER_IMAGE|" model-deployment.yaml | kubectl apply -f -

# Clean-up section
gcloud secrets delete hf-username \
  --quiet \
&& gcloud secrets delete hf-token \
    --quiet \
&& gcloud artifacts repositories delete $REPOSITORY_NAME \
    --location=$REGION \
    --quiet \
&& gcloud projects remove-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com" \
    --role="roles/compute.instanceAdmin.v1" \
    --role="roles/iam.serviceAccountUser" \
    --role="roles/secretmanager.secretAccessor" \
    --condition=None \
&& gsutil -m rm -rf $BUCKET_NAME \
&& gcloud compute images delete $DISK_IMAGE \
    --quiet \
&& gcloud container clusters delete $CLUSTER_NAME \
    --region=$REGION \
    --quiet
