# whereami

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/kubernetes-engine-samples&cloudshell_tutorial=README.md&cloudshell_workspace=whereami/)

`whereami` is a simple Kubernetes-oriented python app for describing the location of the pod serving a request via its attributes (cluster name, cluster region, pod name, namespace, service account, etc). This is useful for a variety of demos where you just need to understand how traffic is getting to and returning from your app.

`whereami`, by default, is a Flask-based python app. It also can operate as a [gRPC](https://grpc.io/) server. The instructions for using gRPC are at the bottom of this document [here](#gRPC-support).

### Observability

Tracing to `whereami` is instrumented via [OpenTelemetry](https://cloud.google.com/trace/docs/setup/python-ot) when in default Flask mode, and will export traces to Cloud Trace when run on GCP. The `TRACE_SAMPLING_RATIO` value in the ConfigMap can be used to configure sampling likelihood.

Prometheus metrics are exposed from `whereami` at `x.x.x.x/metrics` in both Flask and gRPC modes. In gRPC mode, the `metrics` endpoint is exposed on port `8000` via `HTTP`.

> Note: when running the `whereami` pod(s) with [Workload Identity](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity) enabled, make sure that the associated GSA has a role attached to it with permissions to write to Cloud Trace, such as `roles/cloudtrace.agent`

### Simple deployment

`whereami` is a single-container app, designed and packaged to run on Kubernetes. In its simplest form it can be deployed in a single line with only a few parameters.

```bash
$ kubectl run --image=us-docker.pkg.dev/google-samples/containers/gke/whereami:v1.2.24 --expose --port 8080 whereami
```

The `whereami`  pod listens on port `8080` and returns a very simple JSON response that indicates who is responding and where they live. This example assumes you're executing the `curl` command from a pod in the same K8s cluster & namespace (although the following examples show how to access from external clients):

```bash
$ curl 10.12.0.4:8080
{
  "cluster_name": "cfs-limit-test-01", 
  "host_header": "35.232.28.77", 
  "metadata": "frontend", 
  "node_name": "gke-cfs-limit-test-01-default-pool-1b913ea3-poei.c.alexmattson-scratch.internal", 
  "pod_ip": "10.32.0.24", 
  "pod_name": "whereami-6f5545f49c-8thlp", 
  "pod_name_emoji": "👱🏼", 
  "pod_namespace": "default", 
  "pod_service_account": "whereami", 
  "project_id": "alexmattson-scratch", 
  "timestamp": "2020-12-13T05:49:40", 
  "zone": "us-central1-b"
}
```

Some of the returned metadata includes:

- `pod_name_emoji` - an emoji character hashed from Pod name. This makes it a little easier for a human to visually identify the pod you're dealing with.
- `zone` - the GCP zone in which the Pod is running
- `host_header` - the HTTP host header field, as seen by the Pod

### Full deployment walk through

`whereami` can return even more information about your application and its environment, if you provide access to that information. This walkthrough will demonstrate the deployment of a GKE Autopilot cluster and the metadata `whereami` is capable of exposing. Clone this repo to have local access to the deployment files used in step 2.

```bash
$ git clone https://github.com/GoogleCloudPlatform/kubernetes-engine-samples
$ cd kubernetes-engine-samples/quickstarts/whereami
```

#### Step 1 - Create a GKE cluster

First define your environment variables (substituting where #needed#):

```bash
$ export PROJECT_ID=#YOUR_PROJECT_ID#
$ export COMPUTE_REGION=#YOUR_COMPUTE_REGION# # this expects a region, not a zone
$ export CLUSTER_NAME=whereami
```

Now create your [GKE Autopilot](https://cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview) cluster:

```bash
$ gcloud --project ${PROJECT_ID} container clusters \
  create-auto ${CLUSTER_NAME} --region ${COMPUTE_REGION} \
  --release-channel regular
```

This will create a GKE Autopilot cluster in the specified region.

#### Step 2 - Deploy whereami

This [Deployment manifest](k8s/deployment.yaml) shows the configurable parameters of `whereami` as environment variables passed from a configmap to the Pods. Each of the following environment variables are optional. If the environment variable is passed to the Pod then the application will enable that field in its response.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: whereami
spec:
  replicas: 3 #whereami can be deployed as multiple identical replicas
  selector:
    matchLabels:
      app: whereami
  template:
    metadata:
      labels:
        app: whereami
    spec:
      serviceAccountName: whereami
      containers:
      - name: whereami
        image: us-docker.pkg.dev/google-samples/containers/gke/whereami:v1.2.24
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "250m"
        ports:
          - name: http
            containerPort: 8080 #The application is listening on port 8080
        livenessProbe: #There is a health probe listening on port 8080/healthz that will respond with 200 if the application is running
          httpGet:
              path: /healthz
              port: 8080
              scheme: HTTP
          initialDelaySeconds: 5
          periodSeconds: 15
          timeoutSeconds: 5
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8080
            scheme: HTTP
          initialDelaySeconds: 5
          timeoutSeconds: 1
        env:
          - name: NODE_NAME #The node name the pod is running on
            valueFrom:
              fieldRef:
                fieldPath: spec.nodeName
          - name: POD_NAMESPACE #The kubernetes Namespace where the Pod is running
            valueFrom:
              fieldRef:
                fieldPath: metadata.namespace
          - name: POD_IP #The IP address of the pod
            valueFrom:
              fieldRef:
                fieldPath: status.podIP
          - name: POD_SERVICE_ACCOUNT #The name of the Service Account that the pod is using
            valueFrom:
              fieldRef:
                fieldPath: spec.serviceAccountName
          - name: BACKEND_ENABLED #If true, enables queries from whereami to a specified Service name or IP. Requires BACKEND_SERVICE to be set.
            valueFrom:
              configMapKeyRef:
                name: whereami
                key: BACKEND_ENABLED
          - name: BACKEND_SERVICE #Configures the name or IP of the endpoint that whereami will query.
            valueFrom:
              configMapKeyRef:
                name: whereami
                key: BACKEND_SERVICE
          - name: METADATA #An arbitrary metadata field that can be used to label JSON responses
            valueFrom:
              configMapKeyRef:
                name: whereami
                key: METADATA
          - name: HOST
            valueFrom:
              configMapKeyRef:
                name: whereami
                key: HOST
```

The k8s deployment repo uses Kustomize to organize its deployment files. The following command will deploy the all of the required resources for the full `whereami` deployment.

```bash
$ cat k8s/kustomization.yaml
resources:
- ksa.yaml
- deployment.yaml
- service.yaml
- configmap.yaml

$ kubectl apply -k k8s
serviceaccount/whereami created
configmap/whereami created
service/whereami created
deployment.apps/whereami created
```

#### Step 3 - Query whereami

Get the external Service endpoint. The `k8s` repo deploys an external `LoadBalancer Service` on port TCP/80 to make the application reachable on the internet.

```
ENDPOINT=$(kubectl get svc whereami | grep -v EXTERNAL-IP | awk '{ print $4}')
```

> Note: this may be `pending` for a few minutes while the service provisions

Wrap things up by `curl`ing the `EXTERNAL-IP` of the service.

```bash
$ curl $ENDPOINT

{
  "cluster_name": "whereami",
  "gce_instance_id": "2078855064500138887",
  "gce_service_account": "e2m-private-test-01.svc.id.goog",
  "host_header": "34.31.47.190",
  "metadata": "frontend",
  "node_name": "gk3-whereami-pool-2-ba8fb854-gtcq",
  "pod_ip": "10.5.128.86",
  "pod_name": "whereami-78c4df65c8-jwsq9",
  "pod_name_emoji": "🔠",
  "pod_namespace": "default",
  "pod_service_account": "whereami",
  "project_id": "e2m-private-test-01",
  "timestamp": "2024-01-12T05:30:52",
  "zone": "us-central1-c"
}
```

The JSON payload example above covers the majority of fields that `whereami` can return. In the following sections, you will see how it's possible to have `whereami` to call downstream services, adding additional data to that payload. Before you do that, it's worth pointing out that `whereami` can also return individual fields from that JSON payload as plaintext, so long as you include the field's name as a suffix to the path you're calling. Let's see an example.

Suppose you only care about the `pod_name_emoji` value. You can do the following to capture only that value in the response:

```bash
$ curl $ENDPOINT/some/path/prefix/pod_name_emoji

🧚🏽
```

`whereami` will evaluate the path you're accessing, and as long as the last part of the path matches a valid field name of the JSON response, it will return that value. Otherwise, you'll get the full JSON response. 

The fields/path suffixes that are *always* available in a HTTP `whereami` response are:

- `host_header`
- `pod_name`
- `pod_name_emoji`
- `timestamp`


### Setup a backend service call

`whereami` has an optional flag within its configmap that will cause it to call another backend service within your Kubernetes cluster (for example, a different, non-public instance of itself). This is helpful for demonstrating a public microservice call to a non-public microservice, and then including the responses of both microservices in the payload delivered back to the user.

> Note: when defining a backend service to call via HTTP, make sure the `BACKEND_SERVICE` endpoint indicates either an `http://` or `https://` prefix.

#### Step 1 - Deploy the whereami backend

Deploy `whereami` again using the manifests from [k8s-backend-overlay-example](k8s-backend-overlay-example)

```bash
$ kubectl apply -k k8s-backend-overlay-example
serviceaccount/whereami-backend created
configmap/whereami-backend created
service/whereami-backend created
deployment.apps/whereami-backend created
```

`configmap/whereami-backend` has the following fields configured:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: whereami
data:
  BACKEND_ENABLED: "False" # assuming you don't want a chain of backend calls
  METADATA:        "backend"
```

It overlays the base manifest with the following Kustomization file:

```yaml
nameSuffix: "-backend"
labels:
- includeSelectors: true
  includeTemplates: true
  pairs:
    app: whereami-backend
resources:
- ../k8s
patches:
- path: cm-flag.yaml
  target:
    kind: ConfigMap
- path: service-type.yaml
  target:
    kind: Service
```

#### Step 2 - Deploy the whereami frontend

Now we're going to deploy the `whereami` frontend from the `k8s-frontend-overlay-example` folder. The configmap in this folder shows how the frontend is configured differently from the backend:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: whereami
data:
  BACKEND_ENABLED: "True" #This enables requests to be send to the backend
  # when defining the BACKEND_SERVICE using an HTTP protocol, indicate HTTP or HTTPS; if using gRPC, use the host name only
  BACKEND_SERVICE: "http://whereami-backend" #This is the name of the backend Service that was created in the previous step
  METADATA:        "frontend" #This is the metadata string returned in the output
```

Deploy the frontend:

```bash
$ kubectl apply -k k8s-frontend-overlay-example
serviceaccount/whereami-frontend created
configmap/whereami-frontend created
service/whereami-frontend created
deployment.apps/whereami-frontend created
```

#### Step 3 - Query whereami

Get the external Service endpoint again:

```bash
$ ENDPOINT=$(kubectl get svc whereami-frontend | grep -v EXTERNAL-IP | awk '{ print $4}')
```

Curl the endpoint to get the response. In this example we use [jq](https://stedolan.github.io/jq/) to provide a little more structure to the response:

```bash
$ curl $ENDPOINT -s | jq .
{
  "backend_result": {
    "cluster_name": "gke-us-east",
    "host_header": "whereami-backend",
    "metadata": "backend",
    "node_name": "gke-gke-us-east-default-pool-96ad63bd-5bhj.c.church-243723.internal",
    "pod_ip": "10.12.0.9",
    "pod_name": "whereami-backend-769bdff967-6plr6",
    "pod_name_emoji": "🤦🏾‍♀️",
    "pod_namespace": "multi-cluster-demo",
    "pod_service_account": "whereami-backend",
    "project_id": "church-243723",
    "timestamp": "2020-08-02T23:38:56",
    "zone": "us-east4-a"
  },
  "cluster_name": "gke-us-east",
  "host_header": "35.245.36.194",
  "metadata": "frontend",
  "node_name": "gke-gke-us-east-default-pool-96ad63bd-5bhj.c.church-243723.internal",
  "pod_ip": "10.12.0.10",
  "pod_name": "whereami-frontend-5ddd6bc84c-nkrds",
  "pod_name_emoji": "🏃🏻‍♀️",
  "pod_namespace": "multi-cluster-demo",
  "pod_service_account": "whereami-frontend",
  "project_id": "church-243723",
  "timestamp": "2020-08-02T23:38:56",
  "zone": "us-east4-a"
}
```

This response shows the chain of communications with the response from the frontend and the response from the backend. A little bit of jq-magic can actually make it easy too see the chains of communications over successive requests:

```bash
$ for i in {1..3}; do curl $ENDPOINT -s | jq '{frontend: .pod_name_emoji, backend: .backend_result.pod_name_emoji}' -c; done
{"frontend":"🏃🏻‍♀️","backend":"5️⃣"}
{"frontend":"🤦🏾","backend":"🤦🏾‍♀️"}
{"frontend":"🏃🏻‍♀️","backend":"🏀"}
```

### Include all received headers in the response

`whereami` has an additional feature flag that, when enabled, will include all received headers in its reply. If, in `k8s/configmap.yaml`, `ECHO_HEADERS` is set to `True`, the response payload will include a `headers` field, populated with the headers included in the client's request.

#### Step 1 - Deploy whereami with header echoing enabled

```bash
$ kubectl apply -k k8s-echo-headers-overlay-example
serviceaccount/whereami-frontend created
configmap/whereami-frontend created
service/whereami-frontend created
deployment.apps/whereami-frontend created
```

#### Step 2 - Query whereami

Get the external Service endpoint again:

```bash
$ ENDPOINT=$(kubectl get svc whereami-echo-headers | grep -v EXTERNAL-IP | awk '{ print $4}')
```

Curl the endpoint to get the response. Yet again, we use [jq](https://stedolan.github.io/jq/) to provide a little more structure to the response:

```bash
$ curl $ENDPOINT -s | jq .
{
  "cluster_name": "cluster-1",
  "headers": {
    "Accept": "*/*",
    "Host": "35.202.174.251",
    "User-Agent": "curl/7.64.1"
  },
  "host_header": "35.202.174.251",
  "metadata": "echo_headers_enabled",
  "node_name": "gke-cluster-1-default-pool-c91b5644-1z7l.c.alexmattson-scratch.internal",
  "pod_ip": "10.4.1.44",
  "pod_name": "whereami-echo-headers-78766fb94f-ggmcb",
  "pod_name_emoji": "🧑🏿",
  "pod_namespace": "default",
  "pod_service_account": "whereami-echo-headers",
  "project_id": "alexmattson-scratch",
  "timestamp": "2020-08-11T18:21:58",
  "zone": "us-central1-c"
}
```

### gRPC support

All of the prior examples for `whereami` are based on its default operating mode of using [Flask](https://flask.palletsprojects.com/en/1.1.x/) as its server. The following section details how `whereami` can be configured to use [gRPC](https://grpc.io/) instead.

By setting the feature flag `GRPC_ENABLED` in the `whereami` configmap (see [here](k8s-grpc/configmap.yaml)) to `"True"`, `whereami` can be interacted with using [gRPC](https://grpc.io/), with support for the gRPC [health check protocol](https://github.com/grpc/grpc/blob/master/doc/health-checking.md). The examples below leverage [grpcurl](https://github.com/fullstorydev/grpcurl), and assume you've already deployed a GKE cluster.

If gRPC is enabled for a given pod, that `whereami` pod will not respond to HTTP requests, and any downstream service calls that the pod makes will also use gRPC only.

> Note: because gRPC is used as the protocol, the `whereami-grpc` response will omit any `header` fields *and* listens on port `9090` instead of port `8080` by default, but can be configured via the `$PORT` environment variable.

#### Step 1 - Deploy the whereami-grpc backend

Deploy the `whereami-grpc` backend using the manifests from [k8s-grpc-backend-overlay-example](k8s-grpc-backend-overlay-example):

```bash
$ kubectl apply -k k8s-grpc-backend-overlay-example
serviceaccount/whereami-grpc-backend created
configmap/whereami-grpc-backend created
service/whereami-grpc-backend created
deployment.apps/whereami-grpc-backend created
```

This backend will listen for gRPC requests from the frontend service deployed in the following step.

#### Step 2 - Deploy the whereami-grpc frontend

Now we're going to deploy the `whereami-grpc` frontend from the [k8s-grpc-frontend-overlay-example](k8s-grpc-frontend-overlay-example):

```bash
$ kubectl apply -k k8s-grpc-frontend-overlay-example
serviceaccount/whereami-grpc-frontend created
configmap/whereami-grpc-frontend created
service/whereami-grpc-frontend created
deployment.apps/whereami-grpc-frontend created
```

This frontend will both listen for gRPC requests from the user (described in the following step), and will make gRPC requests to the backend deployed in the prior step.

#### Step 3 - Query whereami-grpc frontend

Get the external Service gRPC endpoint:

```bash
$ ENDPOINT=$(kubectl get svc whereami-grpc-frontend | grep -v EXTERNAL-IP | awk '{ print $4}')
```

Call the endpoint using [grpcurl](https://github.com/fullstorydev/grpcurl) to get the response. In this example, we use [jq](https://stedolan.github.io/jq/) to provide a little more structure to the response:

```bash
$ grpcurl -plaintext $ENDPOINT:9090 whereami.Whereami.GetPayload | jq .
{
  "backend_result": {
    "clusterName": "asm-test-01",
    "metadata": "grpc-backend",
    "nodeName": "gke-asm-test-01-default-pool-02e1ecfb-1b9z.c.alexmattson-scratch.internal",
    "podIp": "10.76.0.10",
    "podName": "whereami-grpc-backend-f9b79888d-mcbxv",
    "podNameEmoji": "🤒",
    "podNamespace": "default",
    "podServiceAccount": "whereami-grpc-backend",
    "projectId": "alexmattson-scratch",
    "timestamp": "2020-10-22T05:10:58",
    "zone": "us-central1-c"
  },
  "cluster_name": "asm-test-01",
  "metadata": "grpc-frontend",
  "node_name": "gke-asm-test-01-default-pool-f9ad78c0-w3qr.c.alexmattson-scratch.internal",
  "pod_ip": "10.76.1.10",
  "pod_name": "whereami-grpc-frontend-88b54bc6-9w8cc",
  "pod_name_emoji": "🇸🇦",
  "pod_namespace": "default",
  "pod_service_account": "whereami-grpc-frontend",
  "project_id": "alexmattson-scratch",
  "timestamp": "2020-10-22T05:10:58",
  "zone": "us-central1-f"
}
```

### Notes

#### Cloud Run

When using gRPC for `whereami` on Cloud Run, HTTP/2 must be [enabled](https://cloud.google.com/run/docs/configuring/http2) for the Cloud Run revision.

```bash
$ grpcurl whereami-4uotx33u2a-uc.a.run.app:443  whereami.Whereami/GetPayload
{
  "pod_name": "localhost",
  "pod_name_emoji": "👩🏻‍🔬",
  "project_id": "am-arg-01",
  "timestamp": "2022-12-18T01:55:56",
  "zone": "us-central1-1",
  "gce_instance_id": "0071bb481503eabfa986564835af469bc819c7c1bbb5a262267f5dac714a989324abe2907490f31a0b7baa78e0ccf715b955ee306ae8e6469c83258a01a1c402c8",
  "gce_service_account": "841101411908-compute@developer.gserviceaccount.com"
}
```

When enabling backend in Cloud Run using gRPC:

```bash
$ grpcurl whereami-4uotx33u2a-uc.a.run.app:443  whereami.Whereami/GetPayload
{
  "backend_result": {
    "pod_name": "localhost",
    "pod_name_emoji": "👩🏿‍❤️‍💋‍👨🏼",
    "project_id": "am-arg-01",
    "timestamp": "2022-12-18T04:51:00",
    "zone": "us-central1-1",
    "gce_instance_id": "0071bb481538d20cdd71482479441202997c112a395a4308ee799f7151c31483ded5745b8ddc1cd577e56fbf1458c12dd15cfc55852f12c96ab5dae7590ba15cc4",
    "gce_service_account": "whereami-backend@am-arg-01.iam.gserviceaccount.com"
  },
  "pod_name": "localhost",
  "pod_name_emoji": "👩🏾‍❤️‍👩🏻",
  "project_id": "am-arg-01",
  "timestamp": "2022-12-18T04:51:00",
  "zone": "us-central1-1",
  "gce_instance_id": "0071bb4815da6cf73029c03a21cb16f3fac22031e3f33d3d1749ab2aa683ec2fb83e85151a10908296d54d518352b0b59bba90d39c83ad31d69997e10732e76c34",
  "gce_service_account": "841101411908-compute@developer.gserviceaccount.com"
}
```

#### Buildpacks

If you'd like to build & publish via Google's [buildpacks](https://github.com/GoogleCloudPlatform/buildpacks), something like this should do the trick (leveraging the local `Procfile`) from this directory:

```
cat > run.Dockerfile << EOF
FROM gcr.io/buildpacks/gcp/run:v1
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/* && \
  wget -O /bin/curl https://github.com/moparisthebest/static-curl/releases/download/v8.0.1/curl-amd64 && \
  chmod +x /bin/curl
USER cnb
EOF

docker build -t gcr.io/${PROJECT_ID}/whereami-run-image -f run.Dockerfile .
docker push gcr.io/${PROJECT_ID}/whereami-run-image
```

```pack build --builder gcr.io/buildpacks/builder:v1 --publish gcr.io/${PROJECT_ID}/whereami --run-image gcr.io/${PROJECT_ID}/whereami-run-image```

Recently, [cURL](https://curl.se/) was added to `/bin` of the container image for additional testing capability.


#### Helm

If you'd like to deploy `whereami` via its Helm chart, you could leverage the following instructions.

Deploy the default setup of `whereami` (HTTP frontend):
```sh
helm install whereami oci://us-docker.pkg.dev/google-samples/charts/whereami \
    --version 1.2.24
```

Deploy `whereami` as HTTP backend by running the previous `helm install` command with the following parameters:
```sh
--set suffix=-backend,config.metadata=backend,service.type=ClusterIP
```

Deploy `whereami` as HTTP frontend with backend by running the previous `helm install` command with the following parameters:
```sh
--set suffix=-frontend,config.metadata=frontend,config.backend.enabled=true
```

Deploy `whereami` as echo headers by running the previous `helm install` command with the following parameters:
```sh
--set suffix=-echo-headers,config.metadata=echo_headers_enabled,config.echoHeaders.enabled=true
```

Deploy `whereami` as gRPC frontend by running the previous `helm install` command with the following parameters:
```sh
--set nameOverride=whereami-grpc,config.metadata=grpc-frontend,config.backend.service=whereami-grpc-backend,config.grpc.enabled=true,service.port=9090,service.name=grpc,service.targetPort=9090
```

Deploy `whereami` as gRPC backend by running the previous `helm install` command with the following parameters:
```sh
--set suffix=-backend,nameOverride=whereami-grpc,config.metadata=grpc-backend,config.backend.service=whereami-grpc-backend,config.grpc.enabled=true,service.port=9090,service.name=grpc,service.targetPort=9090,service.type=ClusterIP
```

Deploy `whereami` as gRPC backend with backend by running the previous `helm install` command with the following parameters:
```sh
--set suffix=-frontend,nameOverride=whereami-grpc,config.metadata=grpc-frontend,config.backend.enabled=true,config.backend.service=whereami-grpc-backend,config.grpc.enabled=true,service.port=9090,service.name=grpc,service.targetPort=9090
```