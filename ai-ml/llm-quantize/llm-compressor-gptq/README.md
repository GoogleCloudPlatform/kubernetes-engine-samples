# LLM Quantization on GKE

This document describes how to run LLM quantization on a GKE cluster.

## Prerequisites

- A GKE cluster with NVIDIA H100 GPUs.
- `gcloud` CLI installed and configured.
- `kubectl` CLI installed and configured.

## Steps

1. **Create an Artifact Registry repository:**

   ```bash
   export REPO_NAME=llm-quantize
   export REGION=us-central1
   gcloud artifacts repositories create $REPO_NAME --repository-format=docker --location=$REGION
   ```

2. **Build and push the Docker image:**

   ```bash
   export IMAGE_URL=${REGION}-docker.pkg.dev/$(gcloud config get-value project)/${REPO_NAME}/llm-processor-gptq
   gcloud auth configure-docker ${REGION}-docker.pkg.dev
   gcloud builds submit --tag $IMAGE_URL .
   ```

3. **Set environment variables:**

   ```bash
   export MODEL_ID="meta-llama/Meta-Llama-3-8B-Instruct"
   export HF_TOKEN="your-hugging-face-token"
   ```

4. **Create a Kubernetes secret for the Hugging Face token:**

   ```bash
   kubectl create secret generic hf-secret --from-literal=hf_api_token=$HF_TOKEN
   ```

5. **Deploy the quantization Job to GKE:**

   ```bash
   envsubst < job.yaml | kubectl apply -f -
   ```

6. **Monitor the Job:**

   ```bash
   kubectl get pods -w
   ```

7. **View the logs:**

   ```bash
   kubectl logs -f -l job-name=quantize
   ```
