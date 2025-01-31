# try-gke

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/kubernetes-engine-samples&cloudshell_tutorial=README.md&cloudshell_workspace=try-gke/)

Launch a Kubernetes cluster on Google Kubernetes Engine, run a containerized web
application, and then roll out a new version of the application across the
cluster.

## Setup

1. You will need a Google Cloud Platform account with an active billing account.
   If you don't have one, you can sign up for a free trial to get $300 worth of
   GCP credits, which are valid for 12 months, at
   <a href="https://cloud.google.com/free/" target="_blank">https://cloud.google.com/free/</a>.

2. This tutorial requires the `kubectl` and `gcloud` command-line tools.
   <a href="https://console.cloud.google.com/cloudshell" target="_blank">Cloud Shell</a>
   provides an environment with these tools preinstalled.

For each step below, run the command in a terminal window.

## Step 1: Create a GCP project called "gke-demo".

Enter "Y" to use the recommended project id.

```gcloud projects create --name=gke-demo```


## Step 2: Set the project as the default for this session.

Replace `[PROJECT-ID]` with the id returned in Step 1.

```gcloud config set project [PROJECT-ID]```


## Step 3: Get your billing account ID.

Make a note of the billing account ID in the format XXXXXX-XXXXXX-XXXXXX. If you
see 0 items listed, you can sign up for the
<a href="https://cloud.google.com/free/" target="_blank">Free Trial</a>
to get $300 worth of GCP credits, which are valid for 12 months.

```gcloud alpha billing accounts list```


## Step 4: Enable billing for your project.

Replace `[ACCOUNT-ID]` with the id from step 3.

```gcloud beta billing projects link [PROJECT-ID] --billing-account=[ACCOUNT-ID]```


## Step 5: Enable APIs for your project.

This tutorial requires both the Compute Engine API and Kubernetes Engine API.
This may take a couple of minutes to complete.

```
gcloud services enable compute.googleapis.com; gcloud services enable container.googleapis.com
```


## Step 6: Create a cluster named "demo-1" in GCP zone us-central1-b.

Creating the cluster may take a few minutes.

```
gcloud container clusters create demo-1 -z us-central1-b
```

## Step 7: Deploy a web application from a container image.

A sample container image, `us-docker.pkg.dev/google-samples/containers/gke/hello-app:1.0`, is stored in
Google Artifact Registry.

```
kubectl create deployment web-app \
    --image=us-docker.pkg.dev/google-samples/containers/gke/hello-app:1.0 \
    --port=8080
```


## Step 8: View the pods that were created.

Re-run this command at any time to view the current pod state.

```
kubectl get pods
```


## Step 9: Scale the deployment across three replicas to add redundancy.

```
kubectl scale deployment web-app --replicas 3; kubectl get pods
```


## Step 10: Create an external load balancer Service for the web application.

```
kubectl expose deployment web-app --port=80 --target-port=8080 --type=LoadBalancer
```


## Step 11: Retrieve information about the web-app service.

Make a note of the external IP address that is returned. If the external IP
address is pending, wait a few moments and then re-run the command.

```
kubectl get service web-app
```


## Step 12: Make a request to the application.

Replace `[IP-ADDRESS]` with the external IP address returned in the previous step.

```
curl http://[IP-ADDRESS]
```

## Step 13: Deploy a new version of the web application from Google Container Registry.

```
kubectl set image deployment/web-app hello-app=us-docker.pkg.dev/google-samples/containers/gke/hello-app:2.0
watch kubectl get pods
```

## Step 14: Watch the changes roll out.

Kubernetes will terminate the old pods and re-launch them with the new version.
Appending the `watch` command to **Step 13** ensures that the watch window has
time to open before the deployment completes.

When the changes are complete, click Ctrl+C to return to the main terminal.

## Step 15: Confirm the new version (v2.0.0) has been deployed.

```
curl http://[IP-ADDRESS]
```

## Step 16: Delete the Deployment and Service.

This prevents further charges from accruing to your GCP account.

```
kubectl delete services,deployment web-app
```

Wait about 30 seconds for the Load Balancer to finish deleting in the
background, then move to the next step.

## Step 17: Delete the cluster.

This deletes the cluster and its nodes hosted on Compute Engine.

 ```
 gcloud container clusters delete demo-1 --zone us-central1-b
 ```

## Step 18: Delete the project you created.

Replace `[PROJECT-ID]` with the id returned in Step 1. This prevents further
charges from accruing to your GCP account.

```
gcloud projects delete [PROJECT-ID]
```

--------------------
FURTHER EXPLORATION:

 * [Google Kubernetes Engine (GKE)](https://cloud.google.com/kubernetes-engine/)
 * [GKE tutorials](https://cloud.google.com/kubernetes-engine/docs/tutorials)
 * [Kubernetes comic](https://cloud.google.com/kubernetes-engine/kubernetes-comic/)
 * [Kubernetes documentation](https://kubernetes.io/docs/)
 * [kubectl command syntax](https://kubernetes.io/docs/user-guide/kubectl-overview/)
--------------------
