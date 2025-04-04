# Deploying Wordpress on GKE using Cloud SQL

This guide will show you how to deploy a simple example of Wordpress running on
Google Cloud using Kubernetes and a MySQL database.

## Prerequisites

Before you start, you'll need a Google Cloud project set up.

In the Google Cloud console, on the project selector page, select or create a
Google Cloud project.

> If you don't plan to keep the resources that you create in this procedure,
> create a project instead of selecting an existing project. After you finish
> these steps, you can delete the project, removing all resources associated
> with the project.

Make sure that billing is enabled for your Google Cloud project.

In the Google Cloud console, activate Cloud Shell.

At the bottom of the Google Cloud console, a Cloud Shell session starts and
displays a command-line prompt. Cloud Shell is a shell environment with the
Google Cloud CLI already installed and with values already set for your current
project. It can take a few seconds for the session to initialize.

In Cloud Shell, enable the GKE and Cloud SQL Admin APIs:

```console
gcloud services enable container.googleapis.com sqladmin.googleapis.com
```

You'll also need to install `terraform` and `kubectl` to follow this guide. This
has been tested with `Terraform v1.11.3`, `kubectl v1.31.6` on `linux_amd64`.

## Deploy with Terraform

Open the file `variables.tf`. These are the easily configurable parts of the
solution design. Go over the default values and change them if desired.

To start deploying, initialize terraform by running:

```console
terraform init
```

To deploy your terraform, run:

```console
terraform apply
```

It can take about 15 minutes to provision all the resources and for `terraform
apply` to complete.

The Terraform system will prompt you to enter the name of your Google Cloud
project, as well as a few other configuration variables

You can now use `kubectl` to monitor your deployment.

To get your Wordpress environment's external IP address, run:

```console
kubectl get service wordpress -n default
```

Navigate to this IP address in your browser, and you will be prompted to begin
the Wordpress setup process.

To then destruct this deployment, run:

```console
terraform destroy
```
