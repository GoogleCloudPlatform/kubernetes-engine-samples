# Ray on GKE

This repository contains a Terraform template for installing a Standard or Autopilot GKE cluster in your GCP project.
It sets up the cluster to work seamlessly with the `ray-on-gke`

Platform resources:
* GKE Cluster
* Nvidia GPU drivers
* Kuberay operator and CRDs

## Installation

Preinstall the following on your computer:
* Kubectl
* Terraform 
* Helm
* Gcloud

> **_NOTE:_** Terraform keeps state metadata in a local file called `terraform.tfstate`. Deleting the file may cause some resources to not be cleaned up correctly even if you delete the cluster. We suggest using `terraform destory` before reapplying/reinstalling.

### Platform

1. If needed, git clone this repo

2. `cd kubernetes-engine-samples/ai-ml/gke-ray/gke-platform`

3. Edit `variables.tf` with your Google Cloud settings or `terraform.tfvars` with desired configurations.

4. Run `terraform init`

5. Run `terraform apply`
