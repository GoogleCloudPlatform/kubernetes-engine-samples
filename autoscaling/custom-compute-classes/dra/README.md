# DRA and Custom Compute Class Examples

Custom Compute Classes (CCC) offer a mechanism to manage autoscaling of nodes.
With CCC, the cluster administrator can put nodes into classes designed to meet
specific workload needs. By using classes rather than specific node pools, the
administrator has flexibility to meet the workload needs with different types of
nodes. This can allow autoscaling that prefers spot instances or node shapes for
which the administrator has reservations.

For workloads that utilize specialized devices like GPUs and TPUs, you cannot
always swap out one node shape for another, without adjusting the resource
requirements of the Pod. For example, if a Pod uses the Device Plugin extended
resources to request 2 GPUs (`nvidia.com/gpu: 2`), supplying that Pod with a
node that has a single, larger GPU wouldn't work without updating that Pod spec.

Dynamic Resource Allocation (DRA) is a beta feature in Kubernetes 1.32 which
allows workload authors to more flexibly specify the demands of their workload.
This enables workload authors to write their specifications once, while giving
cluster administrators more options to meet those needs.

## One compute class, many type of GPU nodes

For example, consider an inference workload that has modest latency
requirements, and needs 24GB of GPU memory, 1 vCPU, and 8GB of system memory.
There are a wide variety of node shapes that could run this workload. The
minimum sized shapes with various NVIDIA GPU models that qualify, in the admin's
preferred order, are:

| Node Shape         | vCPUS | Mem (GB) | GPUs     | GPU Mem (GB) |
| -------------------|-------|----------|----------|--------------|
| n1-standard-4+T4   | 4     | 15       | 2 x T4   | 32           |
| g2-standard-4      | 4     | 16       | 1 x L4   | 24           |
| n1-standard-4+P4   | 4     | 15       | 4 x P4   | 32           |
| n1-standard-4+P100 | 4     | 15       | 2 x P100 | 32           |
| n1-standard-4+V100 | 4     | 15       | 2 x V100 | 32           |
| a2-highgpu-1g      | 12    | 85       | 1 x A100 | 40           |
| a3-highgpu-1g      | 26    | 234      | 1 x H100 | 80           |

Given that the A2 and A3 machines are substantially overpowered for this
workload, the cluster admin would prefer that they are not used in this case.
Therefore, they could build a compute class that allows any of the N1 or G2
machines, but prefers them in the order given, for cost savings.

Notice though that some of these machines have 1 GPU, some have 2, and one shape
even has 4 GPUs. Using the current Kubernetes Device Plugin, we would have to
change our `requests` and `limits` for the Pod's `nvidia.com/gpu` extended
resource, or the Pod would not have access to the right number of GPUs, or may
not even schedule.

This is where DRA comes in. Rather than specifying the exact count of GPUs, DRA
allows you to ask for `All` GPUs on the node. If the Pod lands on a node with
one GPU, then that one GPU will be mounted into the Pod; if it lands on one with
4 GPUs, then all 4 will be mounted into the Pod. This flexibility allows the
workload author to create a single Deployment, and for CCC to base autoscaling
on that deployment.

Of course, the workload needs to automatically discover the number and type of
GPU available to it, and make use of them all. But that is a common behavior of many
existing workloads, as long as they are all NVIDIA GPUs.

Let's give this a try. In this example, we will create a compute class that
allows the T4, L4, or P4 options, in that order of priority.

First, we need a GKE cluster with the DRA beta enabled.  This is available
starting in GKE 1.32.

```console
CLUSTER_NAME=drabeta
LOCATION=us-central1-c
VERSION=1.32.0-gke.1358000
gcloud container clusters create \
        --location ${LOCATION} \
        --release-channel rapid \
        --cluster-version ${VERSION} \
        --enable-kubernetes-unstable-apis=resource.k8s.io/v1beta1/deviceclasses,resource.k8s.io/v1beta1/resourceclaims,resource.k8s.io/v1beta1/resourceclaimtemplates,resource.k8s.io/v1beta1/resourceslices \
        ${CLUSTER_NAME}
```

We also need to deploy the [NVIDIA DRA
Driver](https://github.com/NVIDIA/k8s-dra-driver), a pre-production open source
component from NVIDIA. You can clone this repository and run the
[install-dra-driver.sh](https://github.com/NVIDIA/k8s-dra-driver/blob/main/demo/clusters/gke/install-dra-driver.sh)
script to install it on the new cluster. NOTE: This is not sufficient unless
the following two pending PRs have merged:
- [DRA driver update to 1.32](https://github.com/NVIDIA/k8s-dra-driver/pull/220)
  (in particular the updated driver container image in `install-dra-driver.sh`)
- [DRA driver toleration of compute class](https://github.com/NVIDIA/k8s-dra-driver/pull/221)

If those haven't merged, you'll need to make those changes manually to the
script before running it.

There are a few other items in that NVIDIA repository that are relevant. From
the GKE `create-cluster.sh` script, we need to do the following:

```console
# TODO: verify gpu-driver-version=latest makes this unnecessary
#kubectl label node --overwrite -l nvidia.com/gpu.present=true cloud.google.com/gke-gpu-driver-version-
#kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/ubuntu/daemonset-preloaded.yaml

## Create the nvidia namespace
kubectl create namespace nvidia

# Deploy a custom daemonset that prepares a node for use with DRA
# Note, this uses a version from the local directory which adds a toleration
# for the compute class taint. Using the one from the upstream NVIDIA repository
# will not work.
kubectl apply -f prepare-gke-nodes-for-dra.yaml
```

Next, we need node pools representing each machine type. As of now, we cannot use
the Node Autoprovisioning feature of CCC with DRA, because of the specialized
labels needed to switch to the DRA driver. Let's create a node pool for each
machine type. We will create them with a max of three nodes, so we can test the
prioritization functionality without using too many resources:

```console
COMPUTE_CLASS=inference-1x8x24
# N1 with 2xT4
gcloud container node-pools create "n1-standard-4-2xt4" \
        --cluster "${CLUSTER_NAME}" \
        --location "${LOCATION}" \
        --node-version "${VERSION}" \
        --machine-type "n1-standard-4" \
        --accelerator "gpu-driver-version=latest,type=nvidia-tesla-t4,count=2" \
        --image-type "UBUNTU_CONTAINERD" \
        --metadata disable-legacy-endpoints=true \
        --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
        --num-nodes "0" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "3" \
        --node-labels=cloud.google.com/compute-class=${COMPUTE_CLASS},gke-no-default-nvidia-gpu-device-plugin=true,nvidia.com/gpu.present=true \
        --node-taints=cloud.google.com/compute-class=${COMPUTE_CLASS}:NoSchedule

# G2 with 1xL4
gcloud container node-pools create "g2-standard-4" \
        --cluster "${CLUSTER_NAME}" \
        --location "${LOCATION}" \
        --node-version "${VERSION}" \
        --machine-type "g2-standard-4" \
        --accelerator "gpu-driver-version=latest,count=2" \
        --image-type "UBUNTU_CONTAINERD" \
        --metadata disable-legacy-endpoints=true \
        --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
        --num-nodes "0" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "3" \
        --node-labels=cloud.google.com/compute-class=${COMPUTE_CLASS},gke-no-default-nvidia-gpu-device-plugin=true,nvidia.com/gpu.present=true \
        --node-taints=cloud.google.com/compute-class=${COMPUTE_CLASS}:NoSchedule

# N1 with 4xP4
gcloud container node-pools create "n1-standard-4-4xp4" \
        --cluster "${CLUSTER_NAME}" \
        --location "${LOCATION}" \
        --node-version "${VERSION}" \
        --machine-type "n1-standard-4" \
        --accelerator "gpu-driver-version=latest,type=nvidia-tesla-p4,count=4" \
        --image-type "UBUNTU_CONTAINERD" \
        --disk-size "100" \
        --metadata disable-legacy-endpoints=true \
        --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" \
        --num-nodes "0" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "3" \
        --node-labels=cloud.google.com/compute-class=${COMPUTE_CLASS},gke-no-default-nvidia-gpu-device-plugin=true,nvidia.com/gpu.present=true \
        --node-taints=cloud.google.com/compute-class=${COMPUTE_CLASS}:NoSchedule
```

Once we have those node pools defined, we need to create a custom compute class
that prioritizes them in the lowest-cost first order.

```yaml
apiVersion: cloud.google.com/v1
kind: ComputeClass
metadata:
  name: inference-1x8x24
spec:
  priorities:
    - nodepools: [n1-standard-4-2xt4]
    - nodepools: [g2-standard-4]
    - nodepools: [n1-standard-4-4xp4]
  whenUnsatisfiable: DoNotScaleUp
---

```

Now, deploy a workload. We will start with a single replica, which will get
scheduled to one of the nodes we already created above. The following Deployment
can be applied with `kubectl apply -f deployment.yaml`:

```yaml
apiVersion: resource.k8s.io/v1beta1
kind: ResourceClaimTemplate
metadata:
  name: all-gpus
spec:
  spec:
    devices:
      requests:
      - name: gpu
        deviceClassName: gpu.nvidia.com
        allocationMode: All
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ccc-gpu
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ccc-gpu
  template:
    metadata:
      labels:
        app: ccc-gpu
    spec:
      nodeSelector:
        cloud.google.com/compute-class: inference-1x8x24
      containers:
      - name: ctr
        image: ubuntu:22.04
        command: ["bash", "-c"]
        args: ["nvidia-smi -L; trap 'exit 0' TERM; sleep 9999 & wait"]
        resources:
          claims:
          - name: gpu
      resourceClaims:
      - name: gpu
        resourceClaimTemplateName: all-gpus
      tolerations:
      - key: "nvidia.com/gpu"
        operator: "Exists"
        effect: "NoSchedule"
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values:
                      - ccc-gpu
              topologyKey: "kubernetes.io/hostname"
```

Since at present CA does not understand the DRA resources, it won't trigger a
scale up because of insufficient GPU resources. This is in development and will
be resolved soon. Until then, we use an anti-affinity rule to force
one-pod-per-node and trigger scaling.

With just one replica, we see one T4 node spins up:

```console
```
