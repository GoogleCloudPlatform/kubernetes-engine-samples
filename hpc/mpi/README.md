# Run MPI Workloads on GKE H4D

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://ssh.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/GoogleCloudPlatform/kubernetes-engine-samples&cloudshell_tutorial=README.md&cloudshell_workspace=hpc/mpi)

## Overview

This document outlines how to run MPI workloads on H4D GKE.

## Pre-requisites

1. Ensure kubectl is installed on your system: [https://kubernetes.io/docs/tasks/tools/](https://kubernetes.io/docs/tasks/tools/)
2. Install `envsubst` on your system: [https://www.gnu.org/software/gettext/manual/html_node/envsubst-Invocation.html](https://www.gnu.org/software/gettext/manual/html_node/envsubst-Invocation.html)

    ```bash
    sudo apt-get install gettext
    ```

3. Have an existing H4D GKE cluster: See [Create a Cluster](#create-a-cluster)
   * Ensure your cluster has [compact placement](https://cloud.google.com/kubernetes-engine/docs/how-to/compact-placement) for optimal performance.
   * (optional) [Mount a filestore instance](#attach-shared-filesystem) onto your cluster for workloads that require a shared file system.  
   * ensure kubectl context is set to this cluster: See [Set kubectl context to the cluster](#set-kubectl-context-to-the-cluster)
4. Ensure gcloud CLI is installed on your system: [Install gcloud CLI](https://cloud.google.com/sdk/docs/install)
5. Ensure Docker is installed on your system: [Install Docker](https://docs.docker.com/engine/install/)

## Rationale

[Kubeflow MPI Operator](https://www.kubeflow.org/docs/components/trainer/legacy-v1/user-guides/mpi/) is a tool designed to make running allreduce-style distributed training on Kubernetes easy. It can be used to run HPC workloads on GKE. It can save engineering time by handling workload setup and scheduling.

MPI Operator uses yaml configuration files to determine how to execute the workload, and the command to run. It creates a launcher pod and a user specified number of worker pods to run workloads on. The launcher pod is created on a different “layer” than the worker pods, so that clusters/node-pools do not need additional nodes to support the launcher. MPI operator handles scheduling using kueue-batch.

Note that running MPI on GKE will require building an image that supports MPI, SSH, and RDMA. These steps are covered in the next sections.

## Clone the Repo

```bash
git clone https://github.com/GoogleCloudPlatform/kubernetes-engine-samples.git
cd kubernetes-engine-samples/hpc/mpi
```

## Set Environment Variables

```bash
export PROJECT_NAME="PROJECT_NAME" # GCP project where base image will be stored
export REGION="REGION" # region where base image will be stored
export CLUSTER_NAME="CLUSTER_NAME" # name of your H4D GKE cluster
export BUCKET_NAME="BUCKET_NAME" # GCS bucket for blueprint terraform backend
export AUTHORIZED_CIDR_IP="0.0.0.0/0" # IP of machine calling terraform for cluster blueprint cluster creation
export NUM_WORKERS=4 # number of worker nodes in the cluster
export ZONE="ZONE" # zone in which the cluster is based
export AR_REPO="REPOSITORY_NAME" # Artifact Registry repository name where base image will be stored
export IMAGE_NAME="IMAGE_NAME" # base image name
export TAG="TAG" # base image tag
export IMAGE="$REGION-docker.pkg.dev/$PROJECT_NAME/$AR_REPO/$IMAGE_NAME:$TAG"
```

## Create a cluster

If you do not already have a H4D GKE cluster, create one with [Cluster Toolkit blueprint](https://github.com/GoogleCloudPlatform/cluster-toolkit/tree/develop/examples/gke-h4d), or [manually](https://cloud.google.com/kubernetes-engine/docs/how-to/run-hpc-workloads)

clone and make toolkit

```bash
git clone -b develop https://github.com/GoogleCloudPlatform/cluster-toolkit.git
cd cluster-toolkit
make
./gcluster --version
cd ..
```

Substitute environment variables

```bash
envsubst < toolkit-blueprints/gke-h4d-deployment.tpl.yaml > toolkit-blueprints/gke-h4d-deployment.yaml
```

Create the GCS bucket for cluster toolkit deployment

```bash
gcloud storage buckets create gs://$BUCKET_NAME --location=$REGION
```

Create the cluster

```bash
cluster-toolkit/gcluster deploy -d toolkit-blueprints/gke-h4d-deployment.yaml cluster-toolkit/examples/gke-h4d/gke-h4d.yaml
```

(optional) [Attach filesystem for workloads that require shared FS](#attach-shared-filesystem).

* To destroy cluster created with cluster toolkit, run:

```bash
cluster-toolkit/gcluster destroy $CLUSTER_NAME
```

## Set kubectl context to the cluster

Ensure kubectl context and auth-info is set to the desired cluster

```bash
gcloud container clusters get-credentials $CLUSTER_NAME \
    --location=$ZONE
```

## Add taint to node pool

If you created the cluster with toolkit, this is already applied. Add taint to H4D node pool nodes so that only workload pods run on H4D nodes.

```bash
gcloud container node-pools update h4d-highmem-192-lssd-h4d-pool \
    --node-taints="node-type=h4d:NoSchedule" \
    --cluster=$CLUSTER_NAME \
    --location=$ZONE
```

## Install MPI operator

Kubeflow MPI operator will be used to run MPI jobs [Installation instructions](https://github.com/kubeflow/mpi-operator?tab=readme-ov-file#installation).

```bash
kubectl apply --server-side -f https://raw.githubusercontent.com/kubeflow/mpi-operator/v0.6.0/deploy/v2beta1/mpi-operator.yaml
```

## Build user image

Workload pods require an image which supports:

* RDMA  
* MPI (currently only Intel MPI supports RDMA for H4D)  
* SSH  
* Your workload dependencies

Currently H4D GKE supports Rocky Linux only.

We will build a base image that includes RDMA packages and workload dependencies, and use Spack to simplify installation.

### Build the image

```console
docker build -t $IMAGE_NAME .
```

### Push image to Artifact Registry

If target registry does not exist, [create repository](https://cloud.google.com/artifact-registry/docs/repositories/create-repos)

Create and authenticate repository

```bash
gcloud auth login

gcloud artifacts repositories create $AR_REPO \
      --repository-format=docker \
      --location=$REGION

gcloud auth configure-docker $REGION-docker.pkg.dev
```

Push the image to Artifact Registry

```bash
docker tag $IMAGE_NAME $IMAGE
docker push $IMAGE
```

Your hpl image is now available at `$REGION-docker.pkg.dev/$PROJECT_NAME/$REPOSITORY_NAME/$IMAGE_NAME:latest`

## Create workload configuration file

### Basic template

The following is a basic template of an MPI Operator workload config running HPL.  See [MPI Operator Documentation](https://github.com/kubeflow/mpi-operator/blob/master/sdk/python/v2beta1/docs/V2beta1MPIJobSpec.md) for information.

Edit the following:

```bash
export NUM_WORKERS=4
export FI_PROVIDER="verbs;ofi_rxm" # or "tcp" to use TCP
```

```bash
envsubst < hpl-demo.tpl.yaml > hpl-demo.yaml
```

Notes:

* `launcherCreationPolicy: WaitForWorkersReady` causes launcher to be created after worker pods, prevents launcher from running MPI job before workers are ready to connect.  
* Intel MPI requires at least 4 GB of shared memory to run, here we mount a volume of 683Gi of shared memory.  
* The hostfile should be automatically generated and passed to Intel MPI. If Intel MPI does not see the hostfile during mpirun, it should be located at /etc/mpi/hostfile  
* Uncomment `export I_MPI_DEBUG=6` and  `export FI_LOG_LEVEL=warn` to output MPI debug info and libfabric log messages  
* You can check that Intel MPI has been installed properly by running `mpirun -np 2 -ppn 1 IMB-MPI1 PingPong`
* For workloads that require input data and shared access to files, create and attach a [shared filestore instance using Filestore CSI driver](#attach-shared-filesystem).

## Launch and monitor workload

For demonstration, we are running a workload with 4 worker pods (`replicas: 4`).

1. To launch the job, run `kubectl apply -f hpl-demo.yaml`

```bash
kubectl apply -f hpl-demo.yaml
```

Output:

```bash
mpijob.kubeflow.org/hpl-demo created
```

2. Check that the pods have been deployed by running

```bash
kubectl get pods
```

Output:

```bash
NAME                 READY     STATUS              RESTARTS   AGE
hpl-demo-worker-0    1/1       Running             0          Xs
hpl-demo-worker-1    0/1       ContainerCreating   0          Xs
hpl-demo-worker-2    0/1       ContainerCreating   0          Xs
hpl-demo-worker-3    0/1       ContainerCreating   0          Xs
```

The Launcher pod will be created after all worker pods are in Running status

```bash
kubectl get pods
```

Output:

```bash
NAME                     READY     STATUS    RESTARTS     AGE
hpl-demo-launcher-xxxxx  1/1       Running   1 (Xs ago)   Xs
hpl-demo-worker-0        1/1       Running   0            Xs
hpl-demo-worker-1        1/1       Running   0            Xs
hpl-demo-worker-2        1/1       Running   0            Xs
hpl-demo-worker-3        1/1       Running   0            Xs
```

3. Check output using

```bash
kubectl logs -l app=mpi-launcher
```

You should see that HPL is being run

```bash
... # some info
================================================================================
HPLinpack 2.3  --  High-Performance Linpack benchmark  --   December 2, 2018
Written by A. Petitet and R. Clint Whaley,  Innovative Computing Laboratory, UTK
Modified by Piotr Luszczek, Innovative Computing Laboratory, UTK
Modified by Julien Langou, University of Colorado Denver
================================================================================

An explanation of the input/output parameters follows:
T/V    : Wall time / encoded variant.
N      : The order of the coefficient matrix A.
NB     : The partitioning blocking factor.
P      : The number of process rows.
Q      : The number of process columns.
Time   : Time in seconds to solve the linear system.
Gflops : Rate of execution for solving the linear system.

The following parameter values will be used:

N      :  569088 
NB     :     456 
PMAP   : Row-major process mapping
P      :      24 
Q      :      32 
PFACT  :   Crout 
NBMIN  :       4 
NDIV   :       2 
RFACT  :   Crout 
BCAST  :  1ringM 
DEPTH  :       0 
SWAP   : Mix (threshold = 64)
L1     : transposed form
U      : transposed form
EQUIL  : yes
ALIGN  : 8 double precision words

--------------------------------------------------------------------------------

- The matrix A is randomly generated for each test.
- The following scaled residual check will be computed:
      ||Ax-b||_oo / ( eps * ( || x ||_oo * || A ||_oo + || b ||_oo ) * N )
- The relative machine precision (eps) is taken to be               1.110223e-16
- Computational tests pass if scaled residuals are less than                16.0

```

Once the workload is finished running (approximately 45 min), you should see the final output.

```bash
kubectl logs -l app=mpi-launcher
```

```bash
... # some info
================================================================================
HPLinpack 2.3  --  High-Performance Linpack benchmark  --   December 2, 2018
Written by A. Petitet and R. Clint Whaley,  Innovative Computing Laboratory, UTK
Modified by Piotr Luszczek, Innovative Computing Laboratory, UTK
Modified by Julien Langou, University of Colorado Denver
================================================================================

An explanation of the input/output parameters follows:
T/V    : Wall time / encoded variant.
N      : The order of the coefficient matrix A.
NB     : The partitioning blocking factor.
P      : The number of process rows.
Q      : The number of process columns.
Time   : Time in seconds to solve the linear system.
Gflops : Rate of execution for solving the linear system.

The following parameter values will be used:

N      :  569088 
NB     :     456 
PMAP   : Row-major process mapping
P      :      24 
Q      :      32 
PFACT  :   Crout 
NBMIN  :       4 
NDIV   :       2 
RFACT  :   Crout 
BCAST  :  1ringM 
DEPTH  :       0 
SWAP   : Mix (threshold = 64)
L1     : transposed form
U      : transposed form
EQUIL  : yes
ALIGN  : 8 double precision words

--------------------------------------------------------------------------------

- The matrix A is randomly generated for each test.
- The following scaled residual check will be computed:
      ||Ax-b||_oo / ( eps * ( || x ||_oo * || A ||_oo + || b ||_oo ) * N )
- The relative machine precision (eps) is taken to be               1.110223e-16
- Computational tests pass if scaled residuals are less than                16.0

================================================================================
T/V                N    NB     P     Q               Time                 Gflops
--------------------------------------------------------------------------------
WR01C2C4      569088   456    24    32            4026.60             3.0515e+04
HPL_pdgesv() start time Fri Sep  5 01:31:45 2025

HPL_pdgesv() end time   Fri Sep  5 02:38:51 2025

--------------------------------------------------------------------------------
||Ax-b||_oo/(eps*(||A||_oo*||x||_oo+||b||_oo)*N)=   1.14792654e-03 ...... PASSED
================================================================================

Finished      1 tests with the following results:
              1 tests completed and passed residual checks,
              0 tests completed and failed residual checks,
              0 tests skipped because of illegal input values.
--------------------------------------------------------------------------------

End of Tests.
================================================================================
```

## Attach shared filesystem

For workloads that require shared input data or shared file access among nodes, create and attach a shared filestore instance.

Say we want to change the contents of HPL.dat. Due to the containerized nature of GKE, changes to HPL.dat in the image are non-persistent. Instead we can add an HPL.dat to the filestore instance for use in the HPL run.

### \[1\] Enable Filestore CSI driver in your cluster

```bash
gcloud container clusters update $CLUSTER_NAME \
   --update-addons=GcpFilestoreCsiDriver=ENABLED
```

### \[2\] Attach filestore instance

If there is an existing filestore instance you want to attach, [follow this section](https://cloud.google.com/filestore/docs/csi-driver#pvpvc) to attach the instance, then [consume the volume](https://cloud.google.com/filestore/docs/csi-driver#deployment) in your deployment config from the [Create workload configuration file](#create-workload-configuration-file) section.

When attaching existing filestore, the followingis not needed at the end of the deployment config:

```yaml
---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: sharefilespvc
  namespace: default
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: ""
  resources:
    requests:
      storage: 1Ti
```

OR

[Follow this guide](https://cloud.google.com/filestore/docs/csi-driver#create) to create a filestore instance using filestore CSI and PersistentVolumeClaim for the instance, then [consume the volume](https://cloud.google.com/filestore/docs/csi-driver#deployment) in your deployment config from the [Create workload configuration file](#create-workload-configuration-file) section.

Note: Premium tier StorageClass is recommended for optimal performance. [More info on filestore service tiers](https://cloud.google.com/filestore/docs/service-tiers)

#### Mounting the volume in deployment file

[Mount the volume](https://cloud.google.com/filestore/docs/csi-driver#deployment) in the deployment file, it will then be accessible during the workload run at the directory you’ve mounted it at:

```bash
envsubst < hpl-demo-pv.tpl.yaml > hpl-demo-pv.yaml
cat hpl-demo-pv.yaml
```

Upload the custom HPL.dat [file to filestore](https://cloud.google.com/filestore/docs/create-instance-gcloud)

```bash
cat HPL.dat
```

Now you can transfer your HPL.dat to the launcher and worker pod images like this..

```yaml
            args: 
            - |
              # ...
              
              export FI_PROVIDER=$FI_PROVIDER
              export I_MPI_OFI_PROVIDER=$FI_PROVIDER

              # replace default HPL.dat with file in shared FS
              cat /mnt/h4d-filestore/HPL_4_node.dat > /opt/software/linux-broadwell/hpl-2.3-*/bin/HPL.dat

              # ...
```

You can also store workload outputs persistently in the filestore instance like this:

```yaml
            args:
            - |
              # ...

              # set Intel MPI environment variables
              source /opt/software/linux-broadwell/intel-oneapi-mpi-2021.13.1-*/setvars.sh   

              # replace default HPL.dat with file in shared FS
              cat /mnt/h4d-filestore/HPL_4_node.dat > /opt/software/linux-broadwell/hpl-2.3-*/bin/HPL.dat 
              
              # create log file for persistent output storage
              touch /mnt/h4d-filestore/hpl.log

              # run mpijob
              cd /opt/software/linux-broadwell/hpl-2.3-*/bin && mpirun -n $(($NUM_WORKERS * 192)) -ppn 192 ./xhpl >> /mnt/h4d-filestore/hpl.log
```

see `hpl-demo-pv-custom-hpl-dat.tpl.yaml` for example implementation.

## Helpful tips

* You can exec into a pod and run commands with `kubectl exec -it <pod-name> -- /bin/bash -c "<command>"`  
* Keeping jobs to a single nodepool  
  * If there are multiple nodepools in your cluster it’s possible for GKE to schedule one workload onto multiple nodepools. For optimal performance, ensure workers are scheduled in the same nodepool by adding the following to the workers section of the config

```yaml
nodeSelector:
  cloud.google.com/gke-nodepool: NODEPOOL_NAME
```

* Ensure other workloads don’t run on the same node your workload is running on  
  * To prevent other workloads running at the same time in your cluster from scheduling on the same underlying nodes you’re running your workload on, which lowers performance, use [taints and tolerations](http://hpl-demo-launcher-v2w6l). Apply a taint to the nodes you want to reserved for your workload, then add a matching toleration to the worker pods in your workload config. This way only pods with a toleration matching the node taint can be scheduled on those nodes.

* After building the image, you can use `docker run -it $IMAGE_NAME` to run the image interactively and check that everything is installed.

## Known issues

* Environment variables not transferred between SSH sessions  
  * Some workloads (like StarCCM+) start additional SSH sessions. When this happens environment variables are lost for those sessions.

    For these cases it’s recommended to set environment variables in a persistent location like /etc/environment

    Alternatively you can add AcceptEnv LIST\_OF\_ENV\_VARS to sshd config, and SendEnv LIST\_OF\_ENV\_VARS to \~/.ssh/config either when setting up the base image or in the GKE config.

* Error setting up bootstrap proxies  
  * This error may occasionally occur when running workload. This is usually due to the launcher attempting to connect to workers before workers are ready. This can typically be fixed by cancelling and relaunching the workload. If this error occurs consistently, make sure you are using `launcherCreationPolicy: waitForWorkersReady` to ensure launcher only attempts to connect to workers after they are ready.
  
```bash
[mpiexec@mpi-launcher] Error: Unable to run bstrap_proxy on mpi-worker-0.mpi.default.svc (pid 1727524, exit code 768)
[mpiexec@mpi-launcher] poll_for_event (../../../../../src/pm/i_hydra/libhydra/demux/hydra_demux_poll.c:157): check exit codes error 
[mpiexec@mpi-launcher] HYD_dmx_poll_wait_for_proxy_event (../../../../../src/pm/i_hydra/libhydra/demux/hydra_demux_poll.c:206): poll for event error
[mpiexec@mpi-launcher] HYD_bstrap_setup (../../../../../src/pm/i_hydra/libhydra/bstrap/src/intel/i_hydra_bstrap.c:1069): error waiting for event
[mpiexec@mpi-launcher] Error setting up the bootstrap proxies
[mpiexec@mpi-launcher] Possible reasons:
[mpiexec@mpi-launcher] 1. Host is unavailable. Please check that all hosts are available.
[mpiexec@mpi-launcher] 2. Cannot launch hydra_bstrap_proxy or it crashed on one of the hosts.
[mpiexec@mpi-launcher] Make sure hydra_bstrap_proxy is available on all hosts and it has right permissions.
[mpiexec@mpi-launcher] 3. Firewall refused connection.
[mpiexec@mpi-launcher] Check that enough ports are allowed in the firewall and specify them with the I_MPI_PORT_RANGE variable.
[mpiexec@mpi-launcher] 4. Ssh bootstrap cannot launch processes on remote host.
[mpiexec@mpi-launcher] Make sure that passwordless ssh connection is established across compute hosts.
[mpiexec@mpi-launcher] You may try using -bootstrap option to select alternative launcher.
```

* If this error still occurs it’s possible that intel MPI is not set to bootstrap ssh (use `I_MPI_HYDRA_BOOTSTRAP=ssh`), or ssh daemon isn’t set up properly in the user image and/or config.
* Occasionally workloads (like StarCCM+) can automatically rerun once finished, causing loss of logs. For these it’s helpful to add `sleep infinity` after mpirun to prevent this or you to keep worker and launcher pods active if needed.
