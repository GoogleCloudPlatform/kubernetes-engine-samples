#!/bin/bash
REPLICA_COUNT=4

helm install ray-cluster "/Users/pmotgi/exploration/Next 2026/nemo-rl-on-gke/nemoRL" \
  --set values.additionalWorkerGroups.worker-grp-0.replicas=$REPLICA_COUNT