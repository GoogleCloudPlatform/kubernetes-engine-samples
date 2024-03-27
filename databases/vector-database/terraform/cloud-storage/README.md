# Terraform to provision Cloud Storage bucket with corresponding Service Account and bindings

## Prerequisites and Assumptions
* Done initialization of the project and gcloud CLI following the instructions in `{ROOT}/README.md`
* VPC network, refer to `gke` folder for the details

## Usage
```
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
export PROJECT_ID="your project"
export REGION="us-central1"
export CLUSTER_PREFIX="your vector db"

terraform init
terraform plan -var project_id=$PROJECT_ID -var region=${REGION} -var cluster_prefix=${CLUSTER_PREFIX}
terraform apply -var project_id=$PROJECT_ID -var region=${REGION} -var cluster_prefix=${CLUSTER_PREFIX}
```
## Clean up
**NOTE:** Be very careful when destroying any resource, not recommended for production!
```
# Destroy everything
terraform destroy \
-var project_id=$PROJECT_ID \
-var region=${REGION} \
-var cluster_prefix=${CLUSTER_PREFIX}

