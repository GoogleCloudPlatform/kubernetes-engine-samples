#!/usr/bin/env bash
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

COMPUTECLASS_MANIFEST="${1}"
DEPLOYMENT_MANIFEST="${2}"
SCALE_UP_TIMEOUT="${3:-300s}"
SCALE_UP_BATCH="${4:-1}"

echo "Going to use deployment at ${DEPLOYMENT_MANIFEST}, compute class at ${COMPUTECLASS_MANIFEST} with batch scale up size of ${SCALE_UP_BATCH} and timeout: ${SCALE_UP_TIMEOUT}"

kubectl apply -f "${COMPUTECLASS_MANIFEST}"
kubectl apply -f "${DEPLOYMENT_MANIFEST}"

while :; do
    kubectl rollout status -f "${DEPLOYMENT_MANIFEST}" --timeout "${SCALE_UP_TIMEOUT}"
    replicas=$(kubectl get -f "${DEPLOYMENT_MANIFEST}" -o "jsonpath={.status.replicas}")
    newReplicas=$(expr "${replicas}" + "${SCALE_UP_BATCH}")
    echo "Scaling up deployment from ${replicas} to ${newReplicas}"
    kubectl scale -f "${DEPLOYMENT_MANIFEST}" --current-replicas="${replicas}" --replicas="${newReplicas}"
done
