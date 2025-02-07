#!/usr/bin/env sh
# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

echo "**************************************"
echo "Populating queue for batch training..."
echo "**************************************"
echo "The following datasets will be queued for processing:"
filenames=""

# Report all the files containing the training datasets
# and create a concatenated string of filenames to add to the Redis queue
for filepath in datasets/training/*.pkl; do
  echo $filepath
  filenames+=" $filepath"
done

# Push filenames to a Redis queue running on the `redis-leader` GKE Pod
QUEUE_LENGTH=$(kubectl exec redis-leader -- /bin/sh -c \
  "redis-cli rpush datasets ${filenames}")

echo "Queue length: ${QUEUE_LENGTH}"
