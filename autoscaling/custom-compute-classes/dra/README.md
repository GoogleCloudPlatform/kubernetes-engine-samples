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
machines, but prefers them in the order given, for cost savings. It's also
possible to use spot instances for any of these node pools.

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
allows the T4, L4, or P4 options, in that order of priority. We will make the P4
option use spot VMs, to reduce costs.

First, we need a GKE cluster with the DRA beta enabled.  This is available
starting in GKE 1.32. For this example, we will use 1.33:

```console
CLUSTER_NAME=drabeta
LOCATION=us-west4
VERSION=1.33
gcloud container clusters create \
        --location ${LOCATION} \
        --release-channel rapid \
        --cluster-version ${VERSION} \
        --enable-kubernetes-unstable-apis=resource.k8s.io/v1beta1/deviceclasses,resource.k8s.io/v1beta1/resourceclaims,resource.k8s.io/v1beta1/resourceclaimtemplates,resource.k8s.io/v1beta1/resourceslices \
        ${CLUSTER_NAME}
```

When we create node pools in this example, we will use Ubuntu nodes and we will
manually install the NVIDIA GPU drivers, the NVIDIA Container Toolkit, and the
NVIDIA DRA Driver for GPUs.  These are all the components we need to use DRA.

Installing the right NVIDIA drivers for Ubuntu nodes is described in the Google
Cloud GPU
[documentation](https://cloud.google.com/kubernetes-engine/docs/how-to/gpus#ubuntu).
For the GPUs we will use in this example, the following command is sufficient:

```console
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/ubuntu/daemonset-preloaded.yaml
```

The container toolkit is installed via a DaemonSet:

```console
kubectl apply -f nvidia-container-toolkit-installer.yaml
```

The DRA driver is installed via a Helm chart, as described in the Google Cloud
[documentation](https://cloud.google.com/kubernetes-engine/docs/how-to/set-up-dra#install).

```console
kubectl apply -f nvidia-container-toolkit-installer.yaml
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
        --accelerator "type=nvidia-tesla-t4,count=2,gpu-driver-version=disabled" \
        --image-type "UBUNTU_CONTAINERD" \
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
        --accelerator "type=nvidia-l4,gpu-driver-version=disabled" \
        --image-type "UBUNTU_CONTAINERD" \
        --num-nodes "0" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "3" \
        --node-labels=cloud.google.com/compute-class=${COMPUTE_CLASS},gke-no-default-nvidia-gpu-device-plugin=true,nvidia.com/gpu.present=true \
        --node-taints=cloud.google.com/compute-class=${COMPUTE_CLASS}:NoSchedule

# N1 with 4xP4 spot instances
gcloud container node-pools create "n1-standard-4-4xp4" \
        --cluster "${CLUSTER_NAME}" \
        --location "${LOCATION}" \
        --node-version "${VERSION}" \
        --machine-type "n1-standard-4" \
        --accelerator "type=nvidia-tesla-p4,count=4,gpu-driver-version=disabled" \
        --image-type "UBUNTU_CONTAINERD" \
        --num-nodes "0" \
        --enable-autoscaling \
        --min-nodes "0" \
        --max-nodes "3" \
        --spot \
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
scheduled to one of the nodes we already created above. The example creates a
ResourceClaimTemplate that asks for all GPUs on the node, and a Deployment with
a Pod template references that ResourceClaimTemplate. For each Pod created by
the Deployment, a new ResourceClaim will be created based on the
ResourceClaimTemplate, and associated with that new Pod. This will allow
scheduling of the Pod to any node with GPUs, and all the GPUs on that node will
be assigned to the Pod and available to it. To illustrate this, the example uses
`nvidia-smi` to print out all the GPUs it sees.

You can apply this workload with `kubectl apply -f deployment.yaml`.

Since at present CA does not understand the DRA resources, it won't trigger a
scale up because of insufficient GPU resources. This is in development and will
be resolved soon. Until then, we use an anti-affinity rule to force
one-pod-per-node and trigger scaling; you will see this if you examine
`deployment.yaml`.

Results of scaling to 4 replicas:

```console
$ k get po
NAME                       READY   STATUS    RESTARTS   AGE
ccc-gpu-6b6866cb68-66zrl   1/1     Running   0          29s
ccc-gpu-6b6866cb68-prb2k   1/1     Running   0          29s
ccc-gpu-6b6866cb68-rj7z6   1/1     Running   0          29s
ccc-gpu-6b6866cb68-t2jrp   1/1     Running   0          29s
$ k logs ccc-gpu-6b6866cb68-prb2k
GPU 0: Tesla T4 (UUID: GPU-9cbaabad-b724-9242-39e2-486a9450527a)
GPU 1: Tesla T4 (UUID: GPU-3d424488-8672-f8af-3fb7-2ace22ec966e)
$ k logs ccc-gpu-6b6866cb68-66zrl
GPU 0: Tesla T4 (UUID: GPU-3901c076-1e26-f103-4dcd-b3a8d5723bcf)
GPU 1: Tesla T4 (UUID: GPU-4f6e00e5-3d4a-b762-9128-242138949d6f)
$ k logs ccc-gpu-6b6866cb68-rj7z6
GPU 0: Tesla T4 (UUID: GPU-b8d5c02e-d43a-82b4-9219-8d3920fedb0c)
GPU 1: Tesla T4 (UUID: GPU-59057b0c-944b-a66c-7926-89b4cc6c42c8)
$ k logs ccc-gpu-6b6866cb68-t2jrp
GPU 0: NVIDIA L4 (UUID: GPU-51d13b1f-8fe5-9270-be7d-2561dadad56e)
$ k get nodes
NAME                                           STATUS   ROLES    AGE   VERSION
gke-drabeta-default-pool-64569529-32z4         Ready    <none>   26h
v1.32.0-gke.1358000
gke-drabeta-default-pool-64569529-3wmn         Ready    <none>   26h
v1.32.0-gke.1358000
gke-drabeta-default-pool-64569529-57b6         Ready    <none>   26h
v1.32.0-gke.1358000
gke-drabeta-g2-standard-4-68897633-vtd8        Ready    <none>   25m
v1.32.0-gke.1358000
gke-drabeta-n1-standard-4-2xt4-a48308e9-45vl   Ready    <none>   25m
v1.32.0-gke.1358000
gke-drabeta-n1-standard-4-2xt4-a48308e9-92pw   Ready    <none>   28m
v1.32.0-gke.1358000
gke-drabeta-n1-standard-4-2xt4-a48308e9-dnqw   Ready    <none>   25m
v1.32.0-gke.1358000
```
