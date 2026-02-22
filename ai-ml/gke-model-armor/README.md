# Integrate Model Armor guardrails with GKE

These samples show how to secure a Large Language Model (LLM) on Google Kubernetes Engine (GKE) by integrating Model Armor to inspect traffic and defend against harmful inputs and outputs.

The sample includes configurations for:
*   Provisioning a GKE cluster with NVIDIA L4 GPUs and Hyperdisk ML storage.
*   Serving the Gemma 1.1 7b-it model using vLLM.
*   Deploying a GKE Gateway for regional external load balancing.
*   Implementing a security checkpoint using GKE Service Extensions to filter prompts and responses with Model Armor policies.

Visit [https://clouddocs.devsite.corp.google.com/kubernetes-engine/docs/tutorials/integrate-model-armor-guardrails](https://clouddocs.devsite.corp.google.com/kubernetes-engine/docs/tutorials/integrate-model-armor-guardrails) to follow the full tutorial.
