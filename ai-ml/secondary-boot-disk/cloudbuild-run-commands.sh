export PROJECT_ID=$(gcloud config get project) \
&& export REGION=us-central1 \
&& export REPOSITORY_NAME=kfilatau-test-repo \
&& export IMAGE_NAME=gemma-2b-it-test-cropped-v2\
&& export MODEL_PATH=gemma-2b-it






export DISK_IMAGE=gemma-2b-it-test-cropped-image
export CONTAINER_IMAGE=us-central1-docker.pkg.dev/or2-msq-go2-gkes-t1iylu/kfilatau-test-repo/gemma-2b-it-test-cropped:latest
export BUCKET_NAME=gs://kfilatau-cloud-build-logs/
export ZONE=us-central1-a


gcloud builds submit --config cloudbuild-disk.yaml --no-source \
  --substitutions=_DISK_IMAGE=$DISK_IMAGE,_CONTAINER_IMAGE=$CONTAINER_IMAGE,_BUCKET_NAME=$BUCKET_NAME,_ZONE=$ZONE

#  --service-account "projects/$PROJECT_ID/serviceAccounts/compute-default@or2-msq-go2-gkes-t1iylu.iam.gserviceaccount.com"

gcloud builds submit \
  --config cloudbuild-image.yaml \
  --substitutions=_MODEL_PATH=$MODEL_PATH,_PROJECT_ID=$PROJECT_ID,_REPOSITORY_NAME=$REPOSITORY_NAME,_IMAGE_NAME=$IMAGE_NAME
#  --service-account "projects/$PROJECT_ID/serviceAccounts/compute-default@or2-msq-go2-gkes-t1iylu.iam.gserviceaccount.com"


export PJCT_NMBR=$(gcloud projects list --filter="$PROJECT_ID" --format="value(PROJECT_NUMBER)")
gcloud projects add-iam-policy-binding projects/$PROJECT_ID \
    --member="serviceAccount:$PJCT_NMBR@cloudbuild.gserviceaccount.com" \
    --role="roles/compute.instanceAdmin.v1" \
    --role="roles/iam.serviceAccountUser" \
    --condition=None

