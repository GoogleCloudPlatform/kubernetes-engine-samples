# Workload Recommender Module

This repository contains modules to recommend Horizontal Pod Autoscaler
(HPA) or static Vertical Pod Autoscaler (VPA) configurations for Kubernetes
workloads in Google Kubernetes Engine (GKE) based on cost efficiency and
reliability.

## Overview

Workloadrecommender evaluates GKE workloads using historical metric data. It
simulates both HPA and VPA recommendations to determine the best fit for
a given workload.

> **Note:** This solution is currently tested only for Kubernetes
> Deployments.

## Key Features

-   Fetch and aggregate workload CPU and memory metrics from Cloud
    Monitoring.
-   Calculate workload startup time by considering pod initialization and
    cluster autoscaler delays.
-   Simulate resource scaling using DMR (Dynamic Minimum Replicas) and DCR
    (Dynamic CPU Requests) algorithms.
-   Generate resource recommendations for both HPA and VPA.

---

## Required Roles

Ensure you have the following Google Cloud roles:

-   `roles/resourcemanager.projectCreator`
-   `roles/monitoring.viewer`
-   `roles/bigquery.dataOwner`
-   `roles/artifactregistry.creator`
-   `roles/monitoring.admin`

## Create a new monitoring project

For monitoring workloads across multiple projects, it's best to set up a separate
monitoring project. Once you've created this project, you'll need to add your
other projects to its metrics scope. This allows you to receive consolidated
recommendations. Use the following instructions to
[add projects to your metrics scope configuration](https://cloud.google.com/monitoring/settings/multiple-projects)

### Clone repository

```sh
git clone https://github.com/aburhan/kubernetes-engine-samples.git

cd cost-optimization/hpa-config-recommender
```

### Project config

Set environment variables.

```sh
export PROJECT_ID=gke-wa-testmonitoring
export REGION=us-central1
export ARTIFACT_REPO=hpa-config-recommender-repo

gcloud config set project $PROJECT_ID
```

### Enable APIs

- Artifact Registry
- Cloud Asset

```sh
gcloud services enable artifactregistry.googleapis.com \
    cloudasset.googleapis.com
```

### Deploy Terraform instructure

- Bigquery dataset and table
- Artifact registry to store image

```sh
terraform -chdir=deploy init
terraform -chdir=deploy apply -var project_id=$PROJECT_ID -var=region=$REGION -var artifact_registry_id=$ARTIFACT_REPO
```

### Set the pyton package repository

```sh
gcloud config set artifacts/repository $ARTIFACT_REPO
```

#### Configure authentication to Artifact registry

```sh
pip install keyring
pip install keyrings.google-artifactregistry-auth
```

### Install required packages to build and publish the Python package

```sh
pip install twine==6.0.1
pip install build
python -m build
python -m twine upload --repository-url https://$REGION-python.pkg.dev/$PROJECT_ID/$ARTIFACT_REPO/ dist/*
```

## Running Python Notebook

Open the [notebook](notebook.ipynb) and run the workload recommender
