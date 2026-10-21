# JAX Multi-container NUMA-aware workloads on TPU7x (Ironwood)

This example demonstrates how to run a multi-container Pod on a TPU node in GKE for NUMA-aware workloads, specifically using `tpu7x` accelerators (Ironwood).

## Manifest

The `tpu7x-numa-available-chips.yaml` file defines a `Job` that creates a pod with two containers. Each container requests 2 TPU chips.

Each container runs a simple JAX command to verify that it can see the TPU devices allocated to it.

## Prerequisites

- A GKE cluster with a 2x2x2 `tpu7x` node pool.

## Running the example

To run the example, apply the `tpu7x-numa-available-chips.yaml` manifest:

```sh
kubectl apply -f tpu7x-numa-available-chips.yaml
```

Check the logs of the pods to see the output of the JAX command, which should show the number of TPU devices available to each container and across the slice.

```sh
# Replace <pod-name> with the actual pod name from 'kubectl get pods'
kubectl logs <pod-name> -c jax-tpu-1
kubectl logs <pod-name> -c jax-tpu-2
```
