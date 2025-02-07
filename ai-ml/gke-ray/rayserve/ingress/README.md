# Expose your serve endpoint

> NOTE: This is just an example for testing. One scenario you would expose it as an [internal IP](https://cloud.google.com/kubernetes-engine/docs/how-to/deploying-gateways#deploy_a_regional_internal_gateway) that you would call within your VPC. Another scenario if external, you would have Google Cloud [manage a certificate](https://cloud.google.com/kubernetes-engine/docs/how-to/deploying-gateways#deploy_a_global_external_gateway) for you or provide your own.

## Deploy the resources for your gateway
- The gateway resource
```zsh
kubectl apply -f gateway.yaml
```

- Deploy the HTTPRoute resource that will route traffic to your aviary endpoint
```zsh
kubectl apply -f httproute.yaml
```

- Deploy a custom health check policy because the aviary endpoint does not respond with a 200 on "/", however when deployed "/-/routes" does
```zsh
kubectl apply -f healthcheckpolicy.yaml
```

- Check to see what the external IP is in this example
```zsh
EXTERNAL_IP=$(kubectl get gateways.gateway.networking.k8s.io external-http -o=jsonpath="{.status.addresses[0].value}")
echo ${EXTERNAL_IP}
```

- Try the call to your ray serve endpoint now
```zsh
curl http://${EXTERNAL_IP}/meta-llama--Llama-2-7b-chat-hf/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-2-7b-chat-hf",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What are the top 5 most popular programming languages? Please be brief."}
    ],
    "temperature": 0.7
  }'
```