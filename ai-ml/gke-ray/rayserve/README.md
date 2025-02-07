# Serve meta llama2 7b, llama2 70b quantized, falcon 7b-instruct or falcon 40b-instruct quantized models

Use `RayService` and `ray-llm`, which manages a Ray Cluster to load your models for inferencing 

## Get a huggingface token and apply for access to the llama2 model
- Sign up for huggingface account
- Get your read API token
  - Profile -> Settings -> Access Token -> New Token
- Enable access to the [model](https://huggingface.co/meta-llama/Llama-2-7b-chat-hf) on huggingface

## Pre-requisites
- Navigate to the `gke-platform` folder
- Specify values to deploy `L4` GPUs in the cluster, in the `gke-platform` folder.
    - Autopilot
    ```zsh
    cat << EOF > terraform.tfvars
    enable_autopilot=true
    EOF
    ```

    - Standard
    ```zsh
    cat << EOF > terraform.tfvars
    gpu_pool_machine_type="g2-standard-24"
    gpu_pool_accelerator_type="nvidia-l4"
    gpu_pool_node_locations=["us-central1-a", "us-central1-c"]
    EOF
    ```

- Deploy GKE
```zsh
terraform init
terraform apply --auto-approve
```
 
- Return to the `ray-on-gke/rayservice-examples` folder
- Prepare your HF token as a secret
> NOTE: In this example, this is needed for the llama-2 models, not the falcon.
```zsh
export HF_API_TOKEN=<<YOUR_HF_API_TOKEN>>
kubectl create secret generic hf-secret \
    --from-literal=hf_api_token=${HF_API_TOKEN} \
    --dry-run=client -o yaml > hf-secret.yaml
```

- Get context to your GKE cluster
```zsh
gcloud container clusters get-credentials ml-cluster --region us-central1
```

> NOTE: The pre-built rayllm container image has models that references different accelerator types. For this example we are using nvidia `L4` GPUs, so the `spec.serveConfigV2` in `RayService` points to a [repo archive](https://github.com/kenthua/ai-ml) which contains models that uses the `L4` accelerator type. Alternatively, you can build an image as part of the pipeline and include your desired models.

## Instructions for meta llama2 7b or falcon 7b-instruct chat model
This example uses the `rayllm.backend:router_application` to load the model.

- Deploy the RayService, below is the llama2 7b model, but you can change the `rayservice-*` filename to your desired model. llama2 7b or falcon 7b 
    - Autopilot
    ```zsh
    kubectl apply -f hf-secret.yaml
    kubectl apply -f ap_pvc-rayservice.yaml
    kubectl apply -f models/llama2-7b-chat-hf.yaml
    kubectl apply -f ap_llama2-7b.yaml
    ```

    - Standard
    ```zsh
    kubectl apply -f hf-secret.yaml
    kubectl apply -f models/llama2-7b-chat-hf.yaml
    kubectl apply -f llama2-7b.yaml
    ```

- Confirm the model is ready, from status `DEPLOYING` to `RUNNING`
```zsh
export HEAD_POD=$(kubectl get pods --selector=ray.io/node-type=head -n default -o custom-columns=POD:metadata.name --no-headers)

watch --color --interval 5 --no-title "kubectl exec -n default -it $HEAD_POD -- serve status | GREP_COLOR='01;92' egrep --color=always -e '^' -e 'RUNNING'"
```

### Access the serving endpoint
- Port forward the serving port to your local environment
```
kubectl port-forward service/rayllm-serve-svc 8000:8000
```

- Test out the inference endpoint
> NOTE: Change the model below in the json model value to reflect the deployed model. i.e. `tiiuae/falcon-7b`.

```zsh
curl http://localhost:8000/v1/chat/completions \
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

### Test out the endpoint with a sample gradio app

The [sample gradio app](https://github.com/kenthua/gradio-app) at the moment only supports chat completions json spec so it won't work with TGI text spec, which is what the quantized models in the later section uses. If you deploy the gradio application, you do not need the port forward of 8000 above

- Deploy the sample gradio application
> NOTE: If you deploy other models such as the `falcon-7b`, be sure to change the model value in the `gradio.yaml`.

```zsh
kubectl apply -f gradio.yaml
```

- Extract out the external IP of the service to be used. It may take a few minutes for the IP to be available.
```zsh
EXTERNAL_IP=$(kubectl get services gradio \
    --output jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo -e "\nGradio URL: http://${EXTERNAL_IP}\n"
```

## Instructions for meta llama-2 70b chat or falcon 40b-instruct model with 4bit quantization

> NOTE: If you deployed the previous 7b example, it will be overwritten by this example. You will also need the huggingface api token for the falcon 40b-instruct example because it's an input for the huggingface transformer example.

The `spec.serveConfigV2.applications.import_path` points to custom python which uses huggingface transformer `BitsAndBytesConfig` & `AutoModelForCausalLM` libraries to load the quantized model, so that we can fit the 70b or 40b parameter models into 2x `L4` GPUs. This example uses `ray-llm` as the container image though it's not using the `rayllm.backend:router_application` to load the model.

- Deploy the RayService, below is the llama2 70b model, but you can change the `rayservice-*` filename to your desired model. llama2 70b or falcon 40b.
    - Autopilot
    ```zsh
    kubectl apply -f hf-secret.yaml
    kubectl apply -f ap_pvc-rayservice.yaml
    kubectl apply -f models/quantized-model.yaml
    kubectl apply -f ap_llama2-70b.yaml
    ```

    - Standard
    ```zsh
    kubectl apply -f hf-secret.yaml
    kubectl apply -f models/quantized-model.yaml
    kubectl apply -f llama2-70b.yaml
    ```

- Confirm the model is ready, from status `DEPLOYING` to `RUNNING`
```zsh
export HEAD_POD=$(kubectl get pods --selector=ray.io/node-type=head -n default -o custom-columns=POD:metadata.name --no-headers)

watch --color --interval 5 --no-title "kubectl exec -n default -it $HEAD_POD -- serve status | GREP_COLOR='01;92' egrep --color=always -e '^' -e 'RUNNING'"
```

### Access the serving endpoint
- Port forward the serving port to your local environment
```
kubectl port-forward service/rayllm-serve-svc 8000:8000
```

- Test out the inference endpoint
```zsh
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{"text": "What are the top 5 most popular programming languages? Please be brief."}'
```

## Insights & Debugging

Debugging and insights can be made available through Ray either via CLI or UI

### UI

Through the UI, the ray head group provides a layer to view the status of the Ray cluster. It provides observability of your Ray Cluster such as: status, resource consumption, jobs, etc

- Forward the head port 8265 to access the UI
```zsh
export HEAD_POD=$(kubectl get pods --selector=ray.io/node-type=head -n default -o custom-columns=POD:metadata.name --no-headers)

kubectl port-forward pod/$HEAD_POD 8265:8265
```

### CLI

Ray provides both `ray` and `serve` CLI tools to view status of your Ray Cluster

- Exec into the Ray head pod to be able to run the CLI commands
```zsh
export HEAD_POD=$(kubectl get pods --selector=ray.io/node-type=head -n default -o custom-columns=POD:metadata.name --no-headers)

kubectl exec -n default -it $HEAD_POD -- bash
```

Once in the shell of the head pod you can run a few commands

- The status of this Ray cluster
```zsh
ray status
```

Output (do not copy)
```zsh
======== Autoscaler status: 2023-11-13 14:16:18.210554 ========
Node status
---------------------------------------------------------------
Healthy:
 1 node_dc3f939f1b0ed1b731eefe1857bdb2d86fca5a33555a1c32389c4d46
 1 node_9bae5b87f4cee179dabd482d3e13d5df9eb67e728c62d709925688b7
Pending:
 (no pending nodes)
Recent failures:
 (no failures)

Resources
---------------------------------------------------------------
Usage:
 3.0/22.0 CPU (1.0 used of 4.0 reserved in placement groups)
 1.0/3.0 GPU (1.0 used of 1.0 reserved in placement groups)
 0.0/22.0 accelerator_type_cpu
 0.010000000000000018/1.0 accelerator_type_l4 (0.01 used of 0.02 reserved in placement groups)
 0B/26.63GiB memory
 88B/7.87GiB object_store_memory

Demands:
 (no resource demands)
```

- The nodes for this Ray cluster
```zsh
ray list nodes
```

Output (do not copy)
```zsh
======== List: 2023-11-13 14:16:39.406959 ========
Stats:
------------------------------
Total: 2

Table:
------------------------------
    NODE_ID                                                   NODE_IP     IS_HEAD_NODE    STATE    NODE_NAME    RESOURCES_TOTAL                 LABELS
 0  9bae5b87f4cee179dabd482d3e13d5df9eb67e728c62d709925688b7  10.92.0.10  True            ALIVE    10.92.0.10   CPU: 2.0                        ray.io/node_id: 9bae5b87f4cee179dabd482d3e13d5df9eb67e728c62d709925688b7
                                                                                                                GPU: 2.0
                                                                                                                accelerator_type:L4: 1.0
                                                                                                                accelerator_type_cpu: 2.0
                                                                                                                memory: 8.000 GiB
                                                                                                                node:10.92.0.10: 1.0
                                                                                                                node:__internal_head__: 1.0
                                                                                                                object_store_memory: 2.307 GiB
 1  dc3f939f1b0ed1b731eefe1857bdb2d86fca5a33555a1c32389c4d46  10.92.0.11  False           ALIVE    10.92.0.11   CPU: 20.0                       ray.io/node_id: dc3f939f1b0ed1b731eefe1857bdb2d86fca5a33555a1c32389c4d46
                                                                                                                GPU: 1.0
                                                                                                                accelerator_type:L4: 1.0
                                                                                                                accelerator_type_cpu: 20.0
                                                                                                                accelerator_type_l4: 1.0
                                                                                                                memory: 18.626 GiB
                                                                                                                node:10.92.0.11: 1.0
                                                                                                                object_store_memory: 5.561 GiB
```

- The config that Ray serve has loaded
```zsh
serve config
```

Output (do not copy)
```zsh
name: ray-llm
route_prefix: /
import_path: rayllm.backend:router_application
runtime_env:
  working_dir: https://github.com/kenthua/ai-ml/archive/refs/tags/v0.0.5.zip
args:
  models:
  - ./models/meta-llama--Llama-2-7b-chat-hf.yaml
```

- The status of what Ray is serving
```zsh
serve status
```

Output (do not copy)
```zsh
proxies:
  9bae5b87f4cee179dabd482d3e13d5df9eb67e728c62d709925688b7: HEALTHY
  dc3f939f1b0ed1b731eefe1857bdb2d86fca5a33555a1c32389c4d46: HEALTHY
applications:
  ray-llm:
    status: RUNNING
    message: ''
    last_deployed_time_s: 1699909731.439014
    deployments:
      VLLMDeployment:meta-llama--Llama-2-7b-chat-hf:
        status: HEALTHY
        replica_states:
          RUNNING: 1
        message: ''
      Router:
        status: HEALTHY
        replica_states:
          RUNNING: 2
        message: ''
```