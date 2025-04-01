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
