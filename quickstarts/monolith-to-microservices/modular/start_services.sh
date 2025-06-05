# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#!/bin/bash

# Function to start a service
start_service() {
    echo "Starting $1 on port $2..."
    python $1 > $1.log 2>&1 &
    echo "$!" > $1.pid
    sleep 2  # Give some time for the service to start
    if ps -p $! > /dev/null
    then
        echo "$1 started successfully."
    else
        echo "Failed to start $1. Check $1.log for details."
    fi
}

# Start each service
start_service home.py 8080   # Entry point for the home page (books list)
start_service book_details.py 8081  # Book details page
start_service book_reviews.py 8082  # Book reviews service
start_service images.py 8083  # Image serving service

echo "All services have been started. Access the app at http://localhost:8080/"
echo "Use 'kill \$(cat *.pid)' to stop all services."
