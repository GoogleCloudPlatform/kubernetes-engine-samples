## mldiagnostics-webhook-and-operator

It provide helm charts for mldiagnostics webhook and operator, which is needed for integrating mldiagnostics SDK in GKE.



### Install cert-manager if not already installed

Cert-manager is a prerequisite for the injection-webhook. If it’s not installed, follow this to install. After installing cert-manager, it may take up to two minutes for the certificate to become ready.

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update

helm install \
  cert-manager jetstack/cert-manager \
  --namespace cert-manager \
  --create-namespace \
  --version v1.13.0 \
  --set installCRDs=true \
  --set global.leaderElection.namespace=cert-manager \
  --timeout 10m
```

### Install injection-webhook

```bash
helm install mldiagnostics-injection-webhook \
   --namespace=gke-diagon\
   --create-namespace \
  ./injection-webhook/chart

```


### Install connection-operator

```bash
helm install mldiagnostics-connection-operator \
   --namespace=gke-diagon\
   --create-namespace \
  ./connection-operator/chart
```

