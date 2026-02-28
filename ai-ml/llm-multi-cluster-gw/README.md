# Exposing LLM with Multi-cluster Gateway 

This repository contains a shell script and a Terraform template for installing a Standard or Autopilot GKE clusters in your GCP project, register them in a fleet, deploy TGI inference server and set up global external multi-cluster gateway.


Platform resources:
* GKE Clusters
* External Application Load Balancer

## Installation

Preinstall the following on your computer:
* Kubectl
* Terraform 
* Gcloud

> **_NOTE:_** Terraform keeps state metadata in a local file called `terraform.tfstate`. Deleting the file may cause some resources to not be cleaned up correctly even if you delete the cluster. We suggest using script `./remove.sh` before reapplying/reinstalling.

### Platform

1. If needed, git clone this repo

2. `cd kubernetes-engine-samples/ai-ml/llm-multi-cluster-gw`

3. Set up env variables (either in shell or in deploy.sh script)
   PROJECT_ID  - your project id
   REGION_1 - region for first GKE clster
   REGION_2 - region for second GKE cluster
   HF_TOKEN - your HuggingFace API token

4. Run `./deploy.sh`

`./remove.sh` may be used to remove all created resources