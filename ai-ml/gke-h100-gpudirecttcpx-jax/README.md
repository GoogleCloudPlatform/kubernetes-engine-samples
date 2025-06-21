# JAX Mult-Node 'Hello World' on GKE + H100-80GB with GPUDirectTCPx 

This tutorial shows how to run a simple JAX Multi-Node program using NVIDIA GPUs H100-80GB on a GKE cluster with GPUDirectTCPx

## Pre-Requisites

This guide assumes that you already have created a GKE H100 GPUDirectTCPx cluster with GPU drivers.

## Building the image

Build and push the container to your registry. This will push a container to 
`gcr.io/<your project>/jax-pingpong-tcpx:latest`. This might take a few minutes.

```
$ bash build_and_push_container.sh
```

## Run Multi-Node JAX

In kubernetes/jobset.yaml, change <<PROJECT>> by your GCP project name.

Run the JAX application on the compute nodes. This will create 2 pods.

```
$ cd kubernetes
$ kubectl apply -k .
```

Use

```
kubectl get pods

$ kubectl get pods

NAME                       READY   STATUS              RESTARTS   AGE
pingpong-j-0-0-zmcrr    0/2     ContainerCreating   0          5s
pingpong-j-0-1-gw4c5    0/2     ContainerCreating   0          5s
```

to check the status. This will change from `ContainerCreating` to `Pending` (after a few minutes), `Running` and finally `Completed`.

Once the job has completed, use kubectl logs to see the output from one pod

```
$ kubectl logs pingpong-j-0-0-zmcrr
. . .
[16. 16. 16. 16. 16. 16. 16. 16.]
Shutting Down . . .

```

The application creates an array of length 1 equal to [1.0] on each process and then reduces them all. The output, on 16 processes, should be [16.0] on each process.