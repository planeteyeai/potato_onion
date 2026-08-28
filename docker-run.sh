#!/bin/bash

# Build the Docker image
echo "Building Docker image..."
docker build -t potato-onion-intelligence .

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "Build successful! Starting container..."
    # Run the container with port mapping
    docker run -p 8501:8501 --name potato-onion-app potato-onion-intelligence
else
    echo "Build failed!"
    exit 1
fi