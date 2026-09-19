#!/usr/bin/env bash
# Copyright 2026 Google LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Auto-reconnecting Ray Dashboard port forwarder
# Binds local port 8265 to whatever Ray head pod is currently active

echo "============================================================"
echo " Ray Dashboard Forwarder listening on http://localhost:8265"
echo "============================================================"

# Ensure clean start
pkill -f "kubectl port-forward.*8265" 2>/dev/null || true

while true; do
  # Find any running Ray head pod
  POD=$(kubectl get pod -l ray.io/node-type=head --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
  
  if [ -n "$POD" ]; then
    echo "[$(date '+%H:%M:%S')] Connecting Ray Dashboard: $POD:8265 -> http://localhost:8265"
    # Run port-forward. This command blocks until connection drops or pod terminates.
    kubectl port-forward "$POD" 8265:8265 2>&1 | while read -r line; do
      if [[ "$line" == *"Forwarding from"* ]]; then
        echo "[$(date '+%H:%M:%S')] Dashboard connected! Access at: http://localhost:8265"
      elif [[ "$line" == *"error"* ]] || [[ "$line" == *"lost"* ]]; then
        echo "[$(date '+%H:%M:%S')] $line"
      fi
    done
    echo "[$(date '+%H:%M:%S')] Port forward disconnected. Searching for active Ray cluster..."
  fi
  sleep 2
done
