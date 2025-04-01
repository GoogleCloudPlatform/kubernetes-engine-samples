# Monolith to Microservices on GKE


This code accompanies a tutorial series (link will be added once published) that show how to take a monolith, modularize the code, containerize each module, and deploy the container images to a Google Kubernetes Engine (GKE) cluster.

## Contents

This sample contains three versions of the Cymbal Books app:

- `monolith/`: The original monolithic Flask app
- `modular/`: A modular version with separate Flask services communicating over HTTP
- `containerized/`: Dockerized services and a Kubernetes manifest for GKE deployment

## Architecture

The monolith is incrementally broken into four modules:

- **Home app**: Serves the main page and coordinates other services
- **Book details app**: Provides information about books
- **Book reviews app**: Returns user reviews for each book
- **Images app**: Serves book cover images

Each service is containerized and deployed into its own Pod. A corresponding Kubernetes Service enables internal communication.

## Setup

### Prerequisites for the containerize part of the tutorial

- A Google Cloud project with billing enabled

---

### Step 1: Build Container Images

From the `containerized/` directory:

```bash
docker build -t home-app ./home_app
docker build -t book-details-app ./book_details_app
docker build -t book-reviews-app ./book_reviews_app
docker build -t images-app ./images_app
```

### Step 2: Push to Artifact Registry
Replace placeholders with your own values:

```bash
docker tag home-app REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/home-app
docker push REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/home-app
# Repeat for other images...
```

### Step 3: Update Kubernetes Manifest
Edit kubernetes-manifest.yaml and replace image paths with your Artifact Registry URLs:

```bash
# Example
image: us-west1-docker.pkg.dev/my-project/my-repo/home-app:v1
```

### Step 4: Deploy to GKE

```bash
kubectl apply -f kubernetes-manifest.yaml
```

### Step 5: Access the App
After deployment, find the external IP of the home service:

```bash
kubectl get services
```

Then open the app in your browser:

```bash
http://<EXTERNAL-IP>
```

## License
Apache 2.0 © Google LLC

